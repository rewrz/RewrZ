from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..core.config import settings
from ..core.database import get_db
from ..core.media_processor import get_media_processor
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..crud import media as crud_media
from ..models.media import Media as MediaModel
from ..schemas import Media, MediaCreate, MediaUpdate, User

router = APIRouter()
templates = get_templates()

class MediaBulkDeleteRequest(BaseModel):
    media_ids: List[int] = Field(default_factory=list)


UPLOAD_ROOT = Path(settings.MEDIA_UPLOAD_DIR).resolve()
os.makedirs(UPLOAD_ROOT, exist_ok=True)


THUMBNAIL_SIZE_NAMES = ("thumbnail", "small", "medium", "large", "cover")


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


def _media_url_from_filepath(filepath: str, cdn_base: Optional[str] = None) -> str:
    if not filepath:
        return ""
    try:
        relative_path = Path(filepath).resolve().relative_to(UPLOAD_ROOT).as_posix()
    except Exception:
        return ""
    if cdn_base:
        return f"{cdn_base}/{relative_path}"
    return f"/media/{relative_path}"


def _attach_media_url(media_obj: MediaModel, cdn_base: Optional[str] = None) -> MediaModel:
    media_obj.url = _media_url_from_filepath(media_obj.filepath, cdn_base=cdn_base)
    return media_obj


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def _delete_media_files(db_media: MediaModel) -> None:
    original_path = Path(db_media.filepath)
    _safe_unlink(original_path)

    # Thumbnail files are generated under the same month directory: /YYYY/MM/thumbnails/
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


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/media", response_class=HTMLResponse)
async def media_library_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_items = crud_media.get_all_media(db=db)
    cdn_base = _get_media_cdn_base(db)
    for item in media_items:
        _attach_media_url(item, cdn_base=cdn_base)

    return templates.TemplateResponse(
        "admin/media.html",
        {
            "request": request,
            "user": current_user,
            "media_items": media_items,
        },
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media", response_model=List[Media])
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media", response_model=List[Media])
async def get_media_items_api(
    request: Request,
    page: int = 1,
    limit: int = 12,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skip = (page - 1) * limit
    media_items = crud_media.get_all_media(db=db, skip=skip, limit=limit, search=search)
    cdn_base = _get_media_cdn_base(db)
    for item in media_items:
        _attach_media_url(item, cdn_base=cdn_base)
    return media_items


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/media/upload", response_model=Media)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    auto_process: bool = Form(True),
    generate_thumbnails: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_processor = get_media_processor(db)

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

    now = datetime.now()
    sub_dir = Path(now.strftime("%Y")) / now.strftime("%m")
    target_dir = UPLOAD_ROOT / sub_dir
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
        file_type=file_info.get("file_type", "other"),
        mime_type=file.content_type or file_info.get("mime_type") or "application/octet-stream",
        title=title or Path(original_name).stem,
        alt_text=alt_text,
        description=description,
    )

    db_media = crud_media.create_media(db=db, media=media_create, uploaded_by_id=current_user.id)
    cdn_base = _get_media_cdn_base(db)
    _attach_media_url(db_media, cdn_base=cdn_base)

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
        select(MediaModel)
        .filter(MediaModel.id == media_id)
        .options(joinedload(MediaModel.uploaded_by))
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
    media_ids = []
    seen = set()
    for media_id in payload.media_ids or []:
        try:
            value = int(media_id)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        media_ids.append(value)
    if not media_ids:
        raise HTTPException(status_code=400, detail="未提供有效的媒体ID")

    media_items = db.execute(select(MediaModel).filter(MediaModel.id.in_(media_ids))).scalars().all()
    media_map = {item.id: item for item in media_items}

    deletable_items: List[MediaModel] = []
    deletable_ids: List[int] = []
    deleted_ids: List[int] = []
    skipped: List[dict] = []

    for media_id in media_ids:
        db_media = media_map.get(media_id)
        if db_media is None:
            skipped.append({"id": media_id, "reason": "not_found"})
            continue
        if db_media.uploaded_by_id != current_user.id:
            skipped.append({"id": media_id, "reason": "forbidden"})
            continue

        deletable_items.append(db_media)
        deletable_ids.append(media_id)

    if deletable_ids:
        try:
            db.query(MediaModel).filter(MediaModel.id.in_(deletable_ids)).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"批量删除媒体记录失败: {exc}") from exc

        for media_item in deletable_items:
            _delete_media_files(media_item)
        deleted_ids = deletable_ids

    return {
        "requested_count": len(media_ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "skipped": skipped,
    }
