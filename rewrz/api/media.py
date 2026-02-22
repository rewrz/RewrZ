from __future__ import annotations

import hashlib
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from ..core.config import settings
from ..core.database import get_db
from ..core.media_processor import get_media_processor
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import media as crud_media
from ..crud import setting as crud_setting
from ..models import Post as PostModel
from ..models import Setting as SettingModel
from ..models import User as UserModel
from ..models.media import Media as MediaModel
from ..schemas import Media, MediaCreate, MediaUpdate, User

router = APIRouter()
templates = get_templates()


class MediaBulkDeleteRequest(BaseModel):
    media_ids: List[int] = Field(default_factory=list)


class MediaFolderCreateRequest(BaseModel):
    folder: str = Field(..., min_length=1, max_length=160)


class MediaMoveRequest(BaseModel):
    target_folder: str = Field(default="", max_length=160)


class MediaBulkMoveRequest(BaseModel):
    media_ids: List[int] = Field(default_factory=list)
    target_folder: str = Field(default="", max_length=160)


class MediaDuplicateCleanupRequest(BaseModel):
    keep_strategy: str = Field(default="oldest", max_length=16)
    dry_run: bool = False


UPLOAD_ROOT = Path(settings.MEDIA_UPLOAD_DIR).resolve()
os.makedirs(UPLOAD_ROOT, exist_ok=True)

THUMBNAIL_SIZE_NAMES = ("thumbnail", "small", "medium", "large", "cover")
DEFAULT_MEDIA_FOLDERS = ("covers", "avatars", "backgrounds", "articles", "misc")
FILE_HASH_CACHE: Dict[str, Tuple[int, float, str]] = {}
FOLDER_CACHE_TTL_SECONDS = 60
MEDIA_FOLDER_CACHE: Dict[str, Any] = {"expires_at": 0.0, "items": None}


def _get_setting_value(db: Session, key: str, default):
    setting = crud_setting.get_setting(db, key)
    if setting and setting.value:
        return setting.value.get("value", default)
    return default


def _get_media_cdn_base(db: Session) -> Optional[str]:
    enabled = bool(_get_setting_value(db, "media_enable_cdn", False))
    if not enabled:
        return None

    cdn_url = str(_get_setting_value(db, "media_cdn_url", "") or "").strip().rstrip("/")
    if not cdn_url:
        return None
    if not cdn_url.startswith(("http://", "https://")):
        return None
    return cdn_url


def _ensure_default_folders() -> None:
    for folder in DEFAULT_MEDIA_FOLDERS:
        (UPLOAD_ROOT / folder).mkdir(parents=True, exist_ok=True)


def _invalidate_media_folder_cache() -> None:
    MEDIA_FOLDER_CACHE["expires_at"] = 0.0
    MEDIA_FOLDER_CACHE["items"] = None


def _normalize_folder_path(folder: Optional[str]) -> str:
    raw = str(folder or "").strip().replace("\\", "/")
    if raw in {"", "/"}:
        return ""

    parts: List[str] = []
    for part in raw.split("/"):
        token = part.strip()
        if not token or token == ".":
            continue
        if token == "..":
            raise ValueError("文件夹路径不合法")
        if any(char in token for char in (":", "*", "?", '"', "<", ">", "|")):
            raise ValueError("文件夹名称包含非法字符")
        parts.append(token)

    normalized = "/".join(parts)
    target = (UPLOAD_ROOT / normalized).resolve()
    if target != UPLOAD_ROOT and UPLOAD_ROOT not in target.parents:
        raise ValueError("文件夹路径超出媒体目录")
    return normalized


def _relative_media_path(filepath: str) -> str:
    if not filepath:
        return ""
    try:
        return Path(filepath).resolve().relative_to(UPLOAD_ROOT).as_posix()
    except Exception:
        return ""


def _folder_from_filepath(filepath: str) -> str:
    rel_path = _relative_media_path(filepath)
    if not rel_path:
        return ""
    parent = Path(rel_path).parent.as_posix()
    return "" if parent == "." else parent


def _stat_media_file(filepath: str) -> Tuple[str, int]:
    if not filepath:
        return "", 0
    file_path = Path(filepath)
    if not file_path.exists() or not file_path.is_file():
        return "", 0
    try:
        return _compute_sha256_from_file(file_path), int(file_path.stat().st_size)
    except OSError:
        return "", 0


def _media_url_from_filepath(filepath: str, cdn_base: Optional[str] = None) -> str:
    relative_path = _relative_media_path(filepath)
    if not relative_path:
        return ""
    if cdn_base:
        return f"{cdn_base}/{relative_path}"
    return f"/media/{relative_path}"


def _attach_media_url(media_obj: MediaModel, cdn_base: Optional[str] = None) -> MediaModel:
    media_obj.url = _media_url_from_filepath(media_obj.filepath, cdn_base=cdn_base)
    media_obj.folder = str(getattr(media_obj, "folder", "") or _folder_from_filepath(media_obj.filepath))
    if not hasattr(media_obj, "is_duplicate"):
        media_obj.is_duplicate = False
    return media_obj


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def _delete_media_files(db_media: MediaModel) -> None:
    _delete_media_files_by_filepath(db_media.filepath)


def _delete_media_files_by_filepath(filepath: str) -> None:
    if not filepath:
        return
    original_path = Path(filepath)
    try:
        FILE_HASH_CACHE.pop(str(original_path.resolve()), None)
    except Exception:
        pass
    _safe_unlink(original_path)

    thumbnails_dir = original_path.parent / "thumbnails"
    if thumbnails_dir.exists():
        for thumb_file in thumbnails_dir.glob(f"{original_path.stem}_*"):
            _safe_unlink(thumb_file)

    _safe_unlink(original_path.with_suffix(".webp"))


def _cleanup_orphan_media_files(db: Session, cleanup_days: int) -> int:
    if cleanup_days < 1:
        return 0

    tracked_files = db.execute(select(MediaModel.filepath)).scalars().all()
    tracked_paths: Set[str] = set()
    tracked_stems_by_dir: Dict[str, Set[str]] = {}
    for filepath in tracked_files:
        try:
            resolved = Path(filepath).resolve()
        except Exception:
            continue
        tracked_paths.add(str(resolved))
        dir_key = str(resolved.parent)
        if dir_key not in tracked_stems_by_dir:
            tracked_stems_by_dir[dir_key] = set()
        tracked_stems_by_dir[dir_key].add(resolved.stem)

    cutoff = datetime.now() - timedelta(days=cleanup_days)
    deleted_count = 0

    for candidate in UPLOAD_ROOT.rglob("*"):
        if not candidate.is_file():
            continue

        try:
            resolved = candidate.resolve()
        except Exception:
            continue

        resolved_str = str(resolved)
        if resolved_str in tracked_paths:
            continue

        candidate_dir_key = str(resolved.parent)
        if resolved.suffix.lower() == ".webp" and resolved.stem in tracked_stems_by_dir.get(candidate_dir_key, set()):
            continue

        if resolved.parent.name == "thumbnails":
            original_stem = None
            for size_name in THUMBNAIL_SIZE_NAMES:
                suffix = f"_{size_name}"
                if resolved.stem.endswith(suffix):
                    original_stem = resolved.stem[: -len(suffix)]
                    break
            if original_stem:
                parent_dir_key = str(resolved.parent.parent)
                if original_stem in tracked_stems_by_dir.get(parent_dir_key, set()):
                    continue

        try:
            modified_at = datetime.fromtimestamp(resolved.stat().st_mtime)
        except OSError:
            continue
        if modified_at > cutoff:
            continue

        _safe_unlink(resolved)
        deleted_count += 1

    return deleted_count


def _compute_sha256_from_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _compute_sha256_from_file(path: Path) -> str:
    cache_key = str(path.resolve())
    stat = path.stat()
    cached = FILE_HASH_CACHE.get(cache_key)
    if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
        return cached[2]

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    file_hash = digest.hexdigest()
    FILE_HASH_CACHE[cache_key] = (stat.st_size, stat.st_mtime, file_hash)
    return file_hash


def _find_duplicate_media(db: Session, upload_hash: str, file_size: int) -> Optional[MediaModel]:
    if not upload_hash or file_size < 0:
        return None
    media_items = db.execute(
        select(MediaModel)
        .filter(MediaModel.file_hash == upload_hash)
        .filter(MediaModel.file_size == int(file_size))
        .order_by(MediaModel.id.asc())
    ).scalars().all()
    for item in media_items:
        if Path(item.filepath).is_file():
            return item
    return None


def _make_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _move_related_media_files(old_path: Path, new_path: Path) -> None:
    old_webp_path = old_path.with_suffix(".webp")
    if old_webp_path.exists():
        new_webp_path = _make_unique_path(new_path.with_suffix(".webp"))
        shutil.move(str(old_webp_path), str(new_webp_path))

    old_thumb_dir = old_path.parent / "thumbnails"
    if old_thumb_dir.exists():
        new_thumb_dir = new_path.parent / "thumbnails"
        new_thumb_dir.mkdir(parents=True, exist_ok=True)
        for thumb_file in old_thumb_dir.glob(f"{old_path.stem}_*"):
            suffix_part = thumb_file.stem[len(old_path.stem) :]
            new_thumb_path = _make_unique_path(new_thumb_dir / f"{new_path.stem}{suffix_part}{thumb_file.suffix}")
            shutil.move(str(thumb_file), str(new_thumb_path))


def _replace_text_value(text: Any, replacements: List[Tuple[str, str]]) -> Tuple[Any, bool]:
    if not isinstance(text, str) or not text:
        return text, False
    new_value = text
    changed = False
    for old, new in replacements:
        if old and old in new_value:
            new_value = new_value.replace(old, new)
            changed = True
    return new_value, changed


def _replace_nested_value(value: Any, replacements: List[Tuple[str, str]]) -> Tuple[Any, bool]:
    if isinstance(value, str):
        return _replace_text_value(value, replacements)

    if isinstance(value, list):
        changed = False
        next_list = []
        for item in value:
            next_item, item_changed = _replace_nested_value(item, replacements)
            if item_changed:
                changed = True
            next_list.append(next_item)
        return (next_list, True) if changed else (value, False)

    if isinstance(value, dict):
        changed = False
        next_dict: Dict[Any, Any] = {}
        for key, item in value.items():
            next_item, item_changed = _replace_nested_value(item, replacements)
            if item_changed:
                changed = True
            next_dict[key] = next_item
        return (next_dict, True) if changed else (value, False)

    return value, False


def _replace_media_references(db: Session, replacements: List[Tuple[str, str]]) -> Dict[str, int]:
    if not replacements:
        return {"posts": 0, "users": 0, "settings": 0}

    post_changed = 0
    user_changed = 0
    setting_changed = 0

    posts = db.execute(select(PostModel)).scalars().all()
    for post in posts:
        changed = False
        for field in ("featured_image_url", "content_markdown", "content_html"):
            current = getattr(post, field, None)
            updated, has_changed = _replace_text_value(current, replacements)
            if has_changed:
                setattr(post, field, updated)
                changed = True
        if changed:
            post_changed += 1

    users = db.execute(select(UserModel)).scalars().all()
    for user in users:
        updated_avatar, has_changed = _replace_text_value(getattr(user, "avatar_url", None), replacements)
        if has_changed:
            user.avatar_url = updated_avatar
            user_changed += 1

    settings_items = db.execute(select(SettingModel)).scalars().all()
    for setting_item in settings_items:
        current_value = setting_item.value
        updated_value, has_changed = _replace_nested_value(current_value, replacements)
        if has_changed:
            setting_item.value = updated_value
            setting_changed += 1

    return {"posts": post_changed, "users": user_changed, "settings": setting_changed}


def _build_url_replacements(old_filepath: str, new_filepath: str, cdn_base: Optional[str]) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    old_local_url = _media_url_from_filepath(old_filepath, cdn_base=None)
    new_local_url = _media_url_from_filepath(new_filepath, cdn_base=None)
    if old_local_url and new_local_url and old_local_url != new_local_url:
        candidates.append((old_local_url, new_local_url))

    if cdn_base:
        old_cdn_url = _media_url_from_filepath(old_filepath, cdn_base=cdn_base)
        new_cdn_url = _media_url_from_filepath(new_filepath, cdn_base=cdn_base)
        if old_cdn_url and new_cdn_url and old_cdn_url != new_cdn_url:
            candidates.append((old_cdn_url, new_cdn_url))

    if old_filepath and new_filepath and old_filepath != new_filepath:
        candidates.append((old_filepath, new_filepath))

    deduped: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for pair in candidates:
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _sanitize_media_ids(raw_media_ids: List[int]) -> List[int]:
    media_ids: List[int] = []
    seen = set()
    for media_id in raw_media_ids or []:
        try:
            value = int(media_id)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        media_ids.append(value)
    return media_ids


def _parse_media_filter_date(date_text: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    raw = str(date_text or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式不正确，请使用 YYYY-MM-DD") from exc
    if end_of_day:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _move_media_record_to_folder(db_media: MediaModel, target_folder: str) -> Tuple[str, str]:
    old_path = Path(db_media.filepath).resolve()
    if old_path != UPLOAD_ROOT and UPLOAD_ROOT not in old_path.parents:
        raise HTTPException(status_code=400, detail="媒体文件路径无效")
    if not old_path.exists():
        raise HTTPException(status_code=404, detail="媒体文件不存在")

    target_dir = (UPLOAD_ROOT / target_folder).resolve() if target_folder else UPLOAD_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)

    desired_path = target_dir / old_path.name
    if desired_path.resolve() == old_path:
        return str(old_path), str(old_path)

    new_path = _make_unique_path(desired_path)
    shutil.move(str(old_path), str(new_path))
    _move_related_media_files(old_path, new_path)
    db_media.filepath = str(new_path)
    db_media.folder = _folder_from_filepath(db_media.filepath)
    if not db_media.file_hash or int(db_media.file_size or 0) <= 0:
        file_hash, file_size = _stat_media_file(db_media.filepath)
        if file_hash:
            db_media.file_hash = file_hash
        if file_size > 0:
            db_media.file_size = file_size
    return str(old_path), str(new_path)


def _list_media_folders(db: Session) -> List[Dict[str, Any]]:
    _ensure_default_folders()
    now_ts = time.time()
    cached_items = MEDIA_FOLDER_CACHE.get("items")
    expires_at = float(MEDIA_FOLDER_CACHE.get("expires_at") or 0.0)
    if isinstance(cached_items, list) and cached_items and now_ts < expires_at:
        return [dict(item) for item in cached_items]

    folder_rows = db.execute(
        select(MediaModel.folder, func.count(MediaModel.id)).group_by(MediaModel.folder)
    ).all()
    folder_counts: Dict[str, int] = {}
    for folder_value, count_value in folder_rows:
        folder_key = str(folder_value or "")
        folder_counts[folder_key] = int(count_value or 0)

    disk_folders: Set[str] = set()
    for folder_path in UPLOAD_ROOT.rglob("*"):
        if not folder_path.is_dir():
            continue
        try:
            rel = folder_path.resolve().relative_to(UPLOAD_ROOT).as_posix()
        except Exception:
            continue
        if rel and rel != "." and "thumbnails" not in rel.split("/"):
            disk_folders.add(rel)

    all_folders: Set[str] = set(DEFAULT_MEDIA_FOLDERS) | set(folder_counts.keys()) | disk_folders
    all_folders.discard("__all__")

    total_count = sum(folder_counts.values())
    result: List[Dict[str, Any]] = [
        {"path": "__all__", "name": "全部文件夹", "count": total_count},
        {"path": "", "name": "根目录", "count": folder_counts.get("", 0)},
    ]
    for folder in sorted(all_folders):
        if folder == "":
            continue
        result.append(
            {
                "path": folder,
                "name": Path(folder).name,
                "count": folder_counts.get(folder, 0),
            }
        )
    MEDIA_FOLDER_CACHE["items"] = [dict(item) for item in result]
    MEDIA_FOLDER_CACHE["expires_at"] = now_ts + FOLDER_CACHE_TTL_SECONDS
    return result


def _collect_duplicate_groups(
    db: Session,
    current_user_id: int,
    cdn_base: Optional[str],
) -> Dict[str, Any]:
    duplicate_keys_subquery = (
        select(
            MediaModel.file_hash.label("file_hash"),
            MediaModel.file_size.label("file_size"),
        )
        .filter(MediaModel.uploaded_by_id == current_user_id)
        .filter(MediaModel.file_hash != "")
        .filter(MediaModel.file_size > 0)
        .group_by(MediaModel.file_hash, MediaModel.file_size)
        .having(func.count(MediaModel.id) > 1)
        .subquery()
    )

    media_items = (
        db.execute(
            select(MediaModel)
            .join(
                duplicate_keys_subquery,
                and_(
                    MediaModel.file_hash == duplicate_keys_subquery.c.file_hash,
                    MediaModel.file_size == duplicate_keys_subquery.c.file_size,
                ),
            )
            .filter(MediaModel.uploaded_by_id == current_user_id)
            .order_by(MediaModel.uploaded_at.asc(), MediaModel.id.asc())
        )
        .scalars()
        .all()
    )

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in media_items:
        file_hash = str(item.file_hash or "")
        file_size = int(item.file_size or 0)
        if not file_hash or file_size <= 0:
            continue

        key = f"{file_size}:{file_hash}"
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {"hash": file_hash, "size": file_size, "items": []}
            grouped[key] = bucket
        bucket["items"].append(item)

    groups: List[Dict[str, Any]] = []
    total_duplicate_files = 0
    reclaimable_bytes = 0

    for group_info in grouped.values():
        items = group_info["items"]
        if len(items) <= 1:
            continue
        for item in items:
            _attach_media_url(item, cdn_base=cdn_base)

        items_sorted = sorted(items, key=lambda x: (x.uploaded_at or datetime.min, x.id))
        wasted = int(group_info["size"]) * (len(items_sorted) - 1)
        total_duplicate_files += len(items_sorted) - 1
        reclaimable_bytes += wasted
        groups.append(
            {
                "hash": group_info["hash"],
                "size": int(group_info["size"]),
                "count": len(items_sorted),
                "wasted_bytes": wasted,
                "items": [
                    {
                        "id": item.id,
                        "filename": item.filename,
                        "title": item.title or "",
                        "url": getattr(item, "url", ""),
                        "folder": getattr(item, "folder", ""),
                        "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
                    }
                    for item in items_sorted
                ],
            }
        )

    groups.sort(key=lambda x: (x["wasted_bytes"], x["count"]), reverse=True)
    return {
        "group_count": len(groups),
        "total_duplicate_files": total_duplicate_files,
        "reclaimable_bytes": reclaimable_bytes,
        "groups": groups,
    }


def _cleanup_duplicate_groups(
    db: Session,
    current_user: User,
    keep_strategy: str,
    cdn_base: Optional[str],
    dry_run: bool = False,
) -> Dict[str, Any]:
    duplicate_data = _collect_duplicate_groups(db, current_user.id, cdn_base)
    groups = duplicate_data.get("groups", [])

    if keep_strategy not in {"oldest", "latest"}:
        raise HTTPException(status_code=400, detail="keep_strategy 仅支持 oldest 或 latest")

    removed_ids: List[int] = []
    replacements: List[Tuple[str, str]] = []
    reclaimed_bytes = 0

    for group in groups:
        group_items = group.get("items", [])
        if len(group_items) <= 1:
            continue

        keeper = group_items[0] if keep_strategy == "oldest" else group_items[-1]
        keeper_media = crud_media.get_media(db, keeper["id"])
        if keeper_media is None:
            continue
        keeper_path = str(keeper_media.filepath)

        for row in group_items:
            if row["id"] == keeper["id"]:
                continue
            duplicate_media = crud_media.get_media(db, row["id"])
            if duplicate_media is None:
                continue
            if duplicate_media.uploaded_by_id != current_user.id:
                continue

            duplicate_path = str(duplicate_media.filepath)
            file_path = Path(duplicate_path)
            if file_path.exists():
                try:
                    reclaimed_bytes += int(file_path.stat().st_size)
                except OSError:
                    pass

            replacements.extend(_build_url_replacements(duplicate_path, keeper_path, cdn_base))
            removed_ids.append(duplicate_media.id)
            if not dry_run:
                _delete_media_files(duplicate_media)
                db.delete(duplicate_media)

    reference_changes = _replace_media_references(db, replacements)

    if dry_run:
        db.rollback()
    else:
        try:
            db.commit()
            if removed_ids:
                _invalidate_media_folder_cache()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"清理重复文件失败: {exc}") from exc

    return {
        "group_count": duplicate_data.get("group_count", 0),
        "removed_count": len(removed_ids),
        "removed_ids": removed_ids,
        "reclaimed_bytes": reclaimed_bytes,
        "reference_changes": reference_changes,
        "dry_run": dry_run,
    }


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/media", response_class=HTMLResponse)
async def media_library_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_default_folders()
    page_size = 60
    initial_batch = crud_media.get_all_media(db=db, skip=0, limit=page_size + 1)
    has_more = len(initial_batch) > page_size
    media_items = initial_batch[:page_size]
    cdn_base = _get_media_cdn_base(db)
    for item in media_items:
        _attach_media_url(item, cdn_base=cdn_base)

    return templates.TemplateResponse(
        "admin/media.html",
        {
            "request": request,
            "user": current_user,
            "media_items": media_items,
            "media_folders": _list_media_folders(db),
            "media_page_size": page_size,
            "media_has_more": has_more,
        },
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media", response_model=List[Media])
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media", response_model=List[Media])
async def get_media_items_api(
    request: Request,
    page: int = 1,
    limit: int = 12,
    search: Optional[str] = None,
    folder: Optional[str] = None,
    file_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(1, int(page))
    limit = max(1, min(200, int(limit)))
    skip = (page - 1) * limit
    file_type_prefix = (file_type or "").strip().lower() or None
    uploaded_from = _parse_media_filter_date(date_from, end_of_day=False)
    uploaded_to = _parse_media_filter_date(date_to, end_of_day=True)

    folder_filter: Optional[str] = None
    if folder is not None and folder != "__all__":
        try:
            folder_filter = _normalize_folder_path(folder)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_items = crud_media.get_all_media(
        db=db,
        skip=skip,
        limit=limit,
        search=search,
        folder=folder_filter,
        file_type_prefix=file_type_prefix,
        uploaded_from=uploaded_from,
        uploaded_to=uploaded_to,
    )

    cdn_base = _get_media_cdn_base(db)
    for item in media_items:
        _attach_media_url(item, cdn_base=cdn_base)
    return media_items


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/ids", response_model=List[int])
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/ids", response_model=List[int])
async def get_media_item_ids_api(
    request: Request,
    search: Optional[str] = None,
    folder: Optional[str] = None,
    file_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 10000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_type_prefix = (file_type or "").strip().lower() or None
    uploaded_from = _parse_media_filter_date(date_from, end_of_day=False)
    uploaded_to = _parse_media_filter_date(date_to, end_of_day=True)

    folder_filter: Optional[str] = None
    if folder is not None and folder != "__all__":
        try:
            folder_filter = _normalize_folder_path(folder)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return crud_media.get_media_ids(
        db=db,
        search=search,
        folder=folder_filter,
        file_type_prefix=file_type_prefix,
        uploaded_from=uploaded_from,
        uploaded_to=uploaded_to,
        limit=limit,
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/folders")
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/folders")
def get_media_folders_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _list_media_folders(db)


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/folders")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/folders")
def create_media_folder(
    request: Request,
    payload: MediaFolderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    try:
        folder = _normalize_folder_path(payload.folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not folder:
        raise HTTPException(status_code=400, detail="根目录无需创建")

    target_dir = (UPLOAD_ROOT / folder).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    _invalidate_media_folder_cache()
    return {"folder": folder, "message": "文件夹创建成功"}


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/duplicates")
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/duplicates")
def get_duplicate_media_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cdn_base = _get_media_cdn_base(db)
    return _collect_duplicate_groups(db=db, current_user_id=current_user.id, cdn_base=cdn_base)


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/duplicates/cleanup")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/duplicates/cleanup")
def cleanup_duplicate_media_groups(
    request: Request,
    payload: MediaDuplicateCleanupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    cdn_base = _get_media_cdn_base(db)
    return _cleanup_duplicate_groups(
        db=db,
        current_user=current_user,
        keep_strategy=(payload.keep_strategy or "oldest").strip().lower(),
        cdn_base=cdn_base,
        dry_run=bool(payload.dry_run),
    )


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/media/upload", response_model=Media)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    target_folder: Optional[str] = Form(None),
    deduplicate: bool = Form(True),
    auto_process: bool = Form(True),
    generate_thumbnails: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_processor = get_media_processor(db)
    _ensure_default_folders()

    original_name = Path(file.filename or "upload.bin").name
    file_content = await file.read()
    file_size = len(file_content)

    is_valid, error_msg = media_processor.validate_upload_file(
        original_name,
        file_size,
        file.content_type,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        normalized_folder = _normalize_folder_path(target_folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cdn_base = _get_media_cdn_base(db)
    upload_hash = _compute_sha256_from_bytes(file_content)
    if deduplicate:
        duplicate = _find_duplicate_media(db, upload_hash, file_size)
        if duplicate is not None:
            _attach_media_url(duplicate, cdn_base=cdn_base)
            duplicate.is_duplicate = True
            return duplicate

    if normalized_folder:
        target_dir = (UPLOAD_ROOT / normalized_folder).resolve()
    else:
        now = datetime.now()
        target_dir = (UPLOAD_ROOT / now.strftime("%Y") / now.strftime("%m")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{os.urandom(8).hex()}_{original_name}"
    filepath = target_dir / unique_name

    try:
        filepath.write_bytes(file_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc

    file_info = media_processor.get_file_info(str(filepath))

    if file_info.get("file_type") == "image" and auto_process:
        try:
            media_processor.extract_image_metadata(str(filepath))
            if media_processor.auto_compress:
                media_processor.optimize_image(str(filepath))
            if generate_thumbnails:
                thumb_dir = target_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                media_processor.generate_thumbnails(str(filepath), str(thumb_dir))
            if media_processor.enable_webp:
                media_processor.generate_webp_version(str(filepath), str(target_dir))
        except Exception:
            # Processing failures should not block upload persistence.
            pass

    media_create = MediaCreate(
        filename=original_name,
        filepath=str(filepath),
        folder=_folder_from_filepath(str(filepath)),
        file_type=file_info.get("file_type", "other"),
        mime_type=file.content_type or file_info.get("mime_type") or "application/octet-stream",
        file_hash="",
        file_size=0,
        title=title or Path(original_name).stem,
        alt_text=alt_text,
        description=description,
    )
    stored_hash, stored_size = _stat_media_file(str(filepath))
    media_create.file_hash = stored_hash or upload_hash
    media_create.file_size = stored_size or file_size
    db_media = crud_media.create_media(db=db, media=media_create, uploaded_by_id=current_user.id)
    _invalidate_media_folder_cache()

    _attach_media_url(db_media, cdn_base=cdn_base)
    db_media.is_duplicate = False

    auto_cleanup = bool(_get_setting_value(db, "media_auto_cleanup", False))
    if auto_cleanup:
        try:
            cleanup_days = int(_get_setting_value(db, "media_cleanup_days", 30))
        except (TypeError, ValueError):
            cleanup_days = 30
        try:
            _cleanup_orphan_media_files(db, cleanup_days)
        except Exception:
            pass
    return db_media


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", response_model=Media)
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", response_model=Media)
def get_media_item(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_media = db.execute(
        select(MediaModel).filter(MediaModel.id == media_id).options(joinedload(MediaModel.uploaded_by))
    ).scalar_one_or_none()

    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")

    cdn_base = _get_media_cdn_base(db)
    _attach_media_url(db_media, cdn_base=cdn_base)
    return db_media


@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", response_model=Media)
@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", response_model=Media)
def update_media_item(
    request: Request,
    media_id: int,
    media_update: MediaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)

    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this media file")

    updated_media = crud_media.update_media(db=db, media_id=media_id, media_update=media_update)
    cdn_base = _get_media_cdn_base(db)
    _attach_media_url(updated_media, cdn_base=cdn_base)
    return updated_media


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}/move", response_model=Media)
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}/move", response_model=Media)
def move_media_item(
    request: Request,
    media_id: int,
    payload: MediaMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)

    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to move this media file")

    try:
        target_folder = _normalize_folder_path(payload.target_folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    old_filepath, new_filepath = _move_media_record_to_folder(db_media, target_folder)
    cdn_base = _get_media_cdn_base(db)
    replacements = _build_url_replacements(old_filepath, new_filepath, cdn_base)
    _replace_media_references(db, replacements)

    try:
        db.commit()
        db.refresh(db_media)
        _invalidate_media_folder_cache()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"移动媒体失败: {exc}") from exc

    _attach_media_url(db_media, cdn_base=cdn_base)
    return db_media


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/bulk-move")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/bulk-move")
def bulk_move_media_items(
    request: Request,
    payload: MediaBulkMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_ids = _sanitize_media_ids(payload.media_ids)
    if not media_ids:
        raise HTTPException(status_code=400, detail="未提供有效的媒体ID")

    try:
        target_folder = _normalize_folder_path(payload.target_folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_items = db.execute(select(MediaModel).filter(MediaModel.id.in_(media_ids))).scalars().all()
    media_map = {item.id: item for item in media_items}
    moved_ids: List[int] = []
    skipped: List[Dict[str, Any]] = []
    replacements: List[Tuple[str, str]] = []
    cdn_base = _get_media_cdn_base(db)

    for media_id in media_ids:
        db_media = media_map.get(media_id)
        if db_media is None:
            skipped.append({"id": media_id, "reason": "not_found"})
            continue
        if db_media.uploaded_by_id != current_user.id:
            skipped.append({"id": media_id, "reason": "forbidden"})
            continue
        try:
            old_filepath, new_filepath = _move_media_record_to_folder(db_media, target_folder)
            moved_ids.append(media_id)
            replacements.extend(_build_url_replacements(old_filepath, new_filepath, cdn_base))
        except HTTPException as exc:
            skipped.append({"id": media_id, "reason": exc.detail})
        except Exception as exc:
            skipped.append({"id": media_id, "reason": str(exc)})

    _replace_media_references(db, replacements)
    try:
        db.commit()
        if moved_ids:
            _invalidate_media_folder_cache()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量移动失败: {exc}") from exc

    return {
        "requested_count": len(media_ids),
        "moved_count": len(moved_ids),
        "moved_ids": moved_ids,
        "skipped": skipped,
    }


@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_item(
    request: Request,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)

    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this media file")

    _delete_media_files(db_media)
    crud_media.delete_media(db=db, media_id=media_id)
    _invalidate_media_folder_cache()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/bulk-delete")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/bulk-delete")
def bulk_delete_media_items(
    request: Request,
    payload: MediaBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_ids = _sanitize_media_ids(payload.media_ids)
    if not media_ids:
        raise HTTPException(status_code=400, detail="未提供有效的媒体ID")

    media_rows = db.execute(
        select(MediaModel.id, MediaModel.uploaded_by_id, MediaModel.filepath)
        .filter(MediaModel.id.in_(media_ids))
    ).all()
    media_map = {int(row.id): row for row in media_rows}

    deletable_ids: List[int] = []
    deletable_filepaths: List[str] = []
    deleted_ids: List[int] = []
    skipped: List[dict] = []

    for media_id in media_ids:
        media_row = media_map.get(media_id)
        if media_row is None:
            skipped.append({"id": media_id, "reason": "not_found"})
            continue
        if int(media_row.uploaded_by_id or 0) != int(current_user.id):
            skipped.append({"id": media_id, "reason": "forbidden"})
            continue

        deletable_ids.append(media_id)
        if media_row.filepath:
            deletable_filepaths.append(str(media_row.filepath))

    if deletable_ids:
        try:
            db.query(MediaModel).filter(MediaModel.id.in_(deletable_ids)).delete(synchronize_session=False)
            db.commit()
            _invalidate_media_folder_cache()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"批量删除媒体记录失败: {exc}") from exc

        for filepath in deletable_filepaths:
            _delete_media_files_by_filepath(filepath)
        deleted_ids = deletable_ids

    return {
        "requested_count": len(media_ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "skipped": skipped,
    }
