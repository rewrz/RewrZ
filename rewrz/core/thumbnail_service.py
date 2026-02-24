from __future__ import annotations

import hashlib
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlencode, unquote, urlsplit

from PIL import Image, ImageOps, features
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..crud import setting as crud_setting
from ..models.media import Media as MediaModel


@dataclass(frozen=True)
class ThumbnailPreset:
    name: str
    mode: str
    width: int
    height: int
    quality: int
    allow_upscale: bool = False
    background: str = "#FFFFFF"
    version: str = "v1"
    fast_mode: bool = False


@dataclass(frozen=True)
class ThumbnailResult:
    file_path: Path
    mime_type: str
    etag: str
    cache_hit: bool
    preset: str
    dpr: int
    fmt: str


class ThumbnailServiceError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


ALLOWED_DPR = {1, 2}
ALLOWED_FMT = {"auto", "avif", "webp", "jpg", "png"}
MAY_HAVE_ALPHA_MIME = {"image/png", "image/gif", "image/webp", "image/avif"}

DEFAULT_PRESETS: Dict[str, ThumbnailPreset] = {
    "media_lib_card": ThumbnailPreset("media_lib_card", "cover", 256, 256, 72, False, "#FFFFFF", "v2", True),
    "post_cover": ThumbnailPreset("post_cover", "cover", 1200, 630, 82, False, "#FFFFFF", "v1"),
    "post_inline": ThumbnailPreset("post_inline", "contain", 1280, 1280, 82, False, "#FFFFFF", "v1"),
    "avatar": ThumbnailPreset("avatar", "cover", 160, 160, 80, False, "#FFFFFF", "v1"),
    "related_card": ThumbnailPreset("related_card", "cover", 480, 300, 80, False, "#FFFFFF", "v1"),
    "og_cover": ThumbnailPreset("og_cover", "cover", 1200, 630, 86, False, "#FFFFFF", "v1"),
}


_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_NEGATIVE_CACHE: Dict[str, float] = {}
_NEGATIVE_CACHE_GUARD = threading.Lock()
_SETTINGS_CACHE: Dict[str, Tuple[float, Any]] = {}
_SETTINGS_CACHE_GUARD = threading.Lock()
_SETTINGS_CACHE_TTL_SECONDS = 10


def get_preset(name: str) -> ThumbnailPreset:
    preset = DEFAULT_PRESETS.get(str(name or "").strip())
    if preset is None:
        raise ThumbnailServiceError(400, "invalid_preset", f"不支持的缩略图预设: {name}")
    return preset


def build_variant_url(media_id: int, preset: str, dpr: int = 1, fmt: str = "auto") -> str:
    media_value = int(media_id)
    preset_value = str(preset or "").strip()
    if not preset_value:
        raise ThumbnailServiceError(400, "invalid_preset", "预设名称不能为空")
    if dpr not in ALLOWED_DPR:
        raise ThumbnailServiceError(400, "invalid_dpr", "dpr 仅支持 1 或 2")
    fmt_value = str(fmt or "auto").strip().lower()
    if fmt_value not in ALLOWED_FMT:
        raise ThumbnailServiceError(400, "invalid_fmt", "fmt 参数不合法")
    query = {}
    if dpr != 1:
        query["dpr"] = str(dpr)
    if fmt_value != "auto":
        query["fmt"] = fmt_value
    query_part = f"?{urlencode(query)}" if query else ""
    return f"/media/variant/{media_value}/{preset_value}{query_part}"


def is_local_media_url(image_url: str) -> bool:
    if not image_url:
        return False
    try:
        parsed = urlsplit(str(image_url).strip())
    except Exception:
        return False
    return str(parsed.path or "").startswith("/media/")


def resolve_media_id_from_url(db: Session, image_url: str) -> Optional[int]:
    if not image_url:
        return None
    try:
        parsed = urlsplit(str(image_url).strip())
    except Exception:
        return None

    path = unquote(str(parsed.path or ""))
    if not path.startswith("/media/"):
        return None

    # 已经是变体 URL 时直接提取媒体 ID
    if path.startswith("/media/variant/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 4 and parts[0] == "media" and parts[1] == "variant":
            try:
                return int(parts[2])
            except (TypeError, ValueError):
                return None
        return None

    relative_path = path[len("/media/") :].strip("/")
    if not relative_path:
        return None

    source_path = (Path(settings.MEDIA_UPLOAD_DIR) / relative_path).resolve()
    media_id = db.execute(
        select(MediaModel.id).where(MediaModel.filepath == str(source_path))
    ).scalar_one_or_none()
    if media_id is None:
        return None
    try:
        return int(media_id)
    except (TypeError, ValueError):
        return None


def generate_media_variant(
    db: Session,
    media_obj: MediaModel,
    preset_name: str,
    dpr: int = 1,
    fmt: str = "auto",
    accept_header: str = "",
) -> ThumbnailResult:
    if media_obj is None:
        raise ThumbnailServiceError(404, "media_not_found", "媒体不存在")
    if not str(getattr(media_obj, "file_type", "") or "").startswith("image"):
        raise ThumbnailServiceError(415, "unsupported_media_type", "该媒体类型不支持缩略图变体")

    preset = get_preset(preset_name)
    dpr_value = int(dpr)
    if dpr_value not in ALLOWED_DPR:
        raise ThumbnailServiceError(400, "invalid_dpr", "dpr 仅支持 1 或 2")

    source_path = Path(str(media_obj.filepath or "")).resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ThumbnailServiceError(404, "source_missing", "原图文件不存在")

    requested_fmt = str(fmt or "auto").strip().lower()
    if requested_fmt not in ALLOWED_FMT:
        raise ThumbnailServiceError(400, "invalid_fmt", "fmt 参数不合法")
    negotiated_fmt = _resolve_output_format(
        requested_fmt,
        accept_header=accept_header,
        source_mime=str(getattr(media_obj, "mime_type", "") or ""),
    )

    source_hash = str(getattr(media_obj, "file_hash", "") or "").strip()
    if not source_hash:
        source_hash = _compute_sha256(source_path)
    processor_version = _get_setting_str(db, "thumbnail_processor_version", "v1")

    cache_key_plain = (
        f"{source_hash}:{preset.name}:{preset.version}:dpr{dpr_value}:fmt{negotiated_fmt}:{processor_version}"
    )
    cache_key = hashlib.sha256(cache_key_plain.encode("utf-8")).hexdigest()
    ext = _fmt_to_extension(negotiated_fmt)
    cache_root = _resolve_cache_root(db)
    media_id_value = int(getattr(media_obj, "id"))
    cache_path = cache_root / str(media_id_value) / preset.name / f"{cache_key}.{ext}"
    etag = f"\"{cache_key}\""

    if cache_path.exists():
        return ThumbnailResult(
            file_path=cache_path,
            mime_type=_mime_from_ext(cache_path.suffix),
            etag=etag,
            cache_hit=True,
            preset=preset.name,
            dpr=dpr_value,
            fmt=negotiated_fmt,
        )

    negative_ttl = _get_setting_int(db, "thumbnail_negative_cache_ttl_seconds", 30)
    if _is_negative_cached(cache_key):
        raise ThumbnailServiceError(429, "variant_recently_failed", "该变体近期生成失败，请稍后重试")

    lock = _get_lock(cache_key)
    lock_timeout_ms = _get_setting_int(db, "thumbnail_lock_timeout_ms", 15000)
    acquired = lock.acquire(timeout=max(0.1, lock_timeout_ms / 1000))
    if not acquired:
        raise ThumbnailServiceError(429, "variant_busy", "变体生成繁忙，请稍后重试")

    try:
        if cache_path.exists():
            return ThumbnailResult(
                file_path=cache_path,
                mime_type=_mime_from_ext(cache_path.suffix),
                etag=etag,
                cache_hit=True,
                preset=preset.name,
                dpr=dpr_value,
                fmt=negotiated_fmt,
            )

        try:
            _generate_variant_file(
                source_path=source_path,
                output_path=cache_path,
                preset=preset,
                dpr=dpr_value,
                output_fmt=negotiated_fmt,
                megapixel_limit=_get_setting_int(db, "thumbnail_source_max_megapixels", 40),
            )
        except ThumbnailServiceError:
            _set_negative_cache(cache_key, negative_ttl)
            raise
        except Exception as exc:  # pragma: no cover - 防御性兜底
            _set_negative_cache(cache_key, negative_ttl)
            raise ThumbnailServiceError(500, "variant_generate_error", f"生成缩略图失败: {exc}") from exc

        if not cache_path.exists():
            _set_negative_cache(cache_key, negative_ttl)
            raise ThumbnailServiceError(500, "variant_generate_error", "缩略图文件生成失败")

        return ThumbnailResult(
            file_path=cache_path,
            mime_type=_mime_from_ext(cache_path.suffix),
            etag=etag,
            cache_hit=False,
            preset=preset.name,
            dpr=dpr_value,
            fmt=negotiated_fmt,
        )
    finally:
        lock.release()


def purge_media_variant_cache(db: Session, media_id: int) -> None:
    try:
        media_id_value = int(media_id)
    except (TypeError, ValueError):
        return
    cache_root = _resolve_cache_root(db)
    target_dir = cache_root / str(media_id_value)
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)


def _resolve_cache_root(db: Session) -> Path:
    configured = _get_setting_str(db, "thumbnail_cache_dir", "")
    if configured:
        target = Path(configured)
        if not target.is_absolute():
            target = (Path.cwd() / target).resolve()
    else:
        target = (Path(settings.MEDIA_UPLOAD_DIR).resolve() / "_variant_cache")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _get_setting_str(db: Session, key: str, default: str) -> str:
    value = _get_cached_setting_value(db, key, default)
    return str(value)


def _get_setting_int(db: Session, key: str, default: int) -> int:
    value = _get_cached_setting_value(db, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_cached_setting_value(db: Session, key: str, default: Any) -> Any:
    now_ts = time.time()
    with _SETTINGS_CACHE_GUARD:
        cached = _SETTINGS_CACHE.get(key)
        if cached and cached[0] > now_ts:
            return cached[1]

    value: Any = default
    setting = crud_setting.get_setting(db, key)
    if setting and setting.value:
        value = setting.value.get("value", default)

    with _SETTINGS_CACHE_GUARD:
        _SETTINGS_CACHE[key] = (now_ts + _SETTINGS_CACHE_TTL_SECONDS, value)
    return value


def _resolve_output_format(requested_fmt: str, accept_header: str, source_mime: str) -> str:
    if requested_fmt != "auto":
        if requested_fmt == "avif" and not _supports_encoder("avif"):
            raise ThumbnailServiceError(500, "avif_not_supported", "当前环境不支持 AVIF 编码")
        if requested_fmt == "webp" and not _supports_encoder("webp"):
            raise ThumbnailServiceError(500, "webp_not_supported", "当前环境不支持 WebP 编码")
        return requested_fmt

    accept_value = str(accept_header or "").lower()
    if "image/avif" in accept_value and _supports_encoder("avif"):
        return "avif"
    if "image/webp" in accept_value and _supports_encoder("webp"):
        return "webp"

    if str(source_mime or "").lower() in MAY_HAVE_ALPHA_MIME:
        return "png"
    return "jpg"


def _supports_encoder(fmt: str) -> bool:
    normalized = str(fmt or "").lower()
    if normalized == "avif":
        try:
            return bool(features.check("avif"))
        except Exception:
            return False
    if normalized == "webp":
        try:
            return bool(features.check("webp"))
        except Exception:
            return False
    return True


def _fmt_to_extension(fmt: str) -> str:
    fmt_value = str(fmt).lower()
    if fmt_value == "jpeg":
        return "jpg"
    return fmt_value


def _mime_from_ext(ext: str) -> str:
    ext_value = str(ext or "").strip().lower()
    if ext_value == ".jpg" or ext_value == ".jpeg":
        return "image/jpeg"
    if ext_value == ".png":
        return "image/png"
    if ext_value == ".webp":
        return "image/webp"
    if ext_value == ".avif":
        return "image/avif"
    return "application/octet-stream"


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def _is_negative_cached(key: str) -> bool:
    now_ts = time.time()
    with _NEGATIVE_CACHE_GUARD:
        expired_keys = [item_key for item_key, expire_at in _NEGATIVE_CACHE.items() if expire_at <= now_ts]
        for expired_key in expired_keys:
            _NEGATIVE_CACHE.pop(expired_key, None)
        expire_at = _NEGATIVE_CACHE.get(key)
        return bool(expire_at and expire_at > now_ts)


def _set_negative_cache(key: str, ttl_seconds: int) -> None:
    ttl = max(1, int(ttl_seconds))
    with _NEGATIVE_CACHE_GUARD:
        _NEGATIVE_CACHE[key] = time.time() + ttl


def _generate_variant_file(
    source_path: Path,
    output_path: Path,
    preset: ThumbnailPreset,
    dpr: int,
    output_fmt: str,
    megapixel_limit: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resample = Image.Resampling.BILINEAR if preset.fast_mode else Image.Resampling.LANCZOS

    with Image.open(source_path) as image_obj:
        image_obj = ImageOps.exif_transpose(image_obj)
        pixel_count = int(image_obj.width * image_obj.height)
        max_pixels = max(1, int(megapixel_limit)) * 1_000_000
        if pixel_count > max_pixels:
            raise ThumbnailServiceError(422, "source_too_large", "原图像素超出处理上限")

        target_width = max(1, int(preset.width * dpr))
        target_height = max(1, int(preset.height * dpr))

        if not preset.allow_upscale:
            target_width = min(target_width, image_obj.width)
            target_height = min(target_height, image_obj.height)
            target_width = max(1, target_width)
            target_height = max(1, target_height)

        if preset.mode == "cover":
            rendered = ImageOps.fit(
                image_obj,
                (target_width, target_height),
                method=resample,
                centering=(0.5, 0.5),
            )
        elif preset.mode == "contain":
            rendered = image_obj.copy()
            rendered.thumbnail((target_width, target_height), resample)
        elif preset.mode == "fill":
            rendered = image_obj.resize((target_width, target_height), resample)
        else:
            raise ThumbnailServiceError(400, "invalid_preset_mode", f"不支持的预设模式: {preset.mode}")

        save_format = output_fmt.upper()
        save_kwargs: Dict[str, object] = {"optimize": not preset.fast_mode}
        if output_fmt in {"jpg", "jpeg"}:
            save_format = "JPEG"
            save_kwargs["quality"] = max(1, min(100, int(preset.quality)))
            save_kwargs["progressive"] = not preset.fast_mode
            if rendered.mode in ("RGBA", "LA"):
                background = Image.new("RGB", rendered.size, preset.background)
                background.paste(rendered, mask=rendered.split()[-1])
                rendered = background
            elif rendered.mode != "RGB":
                rendered = rendered.convert("RGB")
        elif output_fmt == "png":
            save_format = "PNG"
            save_kwargs["compress_level"] = 6
        elif output_fmt in {"webp", "avif"}:
            save_kwargs["quality"] = max(1, min(100, int(preset.quality)))
        else:
            raise ThumbnailServiceError(400, "invalid_fmt", f"不支持的输出格式: {output_fmt}")

        temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
        rendered.save(temp_path, format=save_format, **save_kwargs)
        temp_path.replace(output_path)
