"""
媒体设置 API 模块

提供媒体配置管理的 HTTP 接口，包括：
1. 媒体设置页面
2. 媒体配置读取和更新
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..core.admin_path import get_admin_path, get_request_admin_path
from ..core.database import get_db
from ..core.media_config import get_media_settings_schema
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_context import DEFAULT_BASE_SETTINGS
from ..core.template_filters import get_templates
from ..crud import setting as crud_setting
from ..schemas import SettingCreate, SettingUpdate, User

router = APIRouter()
templates = get_templates()
ADMIN_PATH = get_admin_path()


def _get_setting_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "string"


def _form_bool(form: Dict[str, Any], key: str, default: bool = False) -> bool:
    if key not in form:
        return bool(default)
    value = str(form.get(key, "")).strip().lower()
    return value in {"1", "true", "on", "yes"}


def _form_int(form: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(str(form.get(key, default)).strip())
    except (TypeError, ValueError):
        return int(default)


def _form_float(form: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(str(form.get(key, default)).strip())
    except (TypeError, ValueError):
        return float(default)


def _form_text(form: Dict[str, Any], key: str, default: str = "") -> str:
    return str(form.get(key, default) or "").strip()


def _normalize_csv_text(raw: str) -> str:
    items = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    return ",".join(items)


async def media_settings_page(
    request: Request,
    db: Session,
    current_user: User,
):
    media_settings = {}
    settings_schema = get_media_settings_schema()

    all_settings = crud_setting.get_settings_by_category(db, "media")
    for setting in all_settings:
        media_settings[setting.key] = setting.value.get("value") if setting.value else None

    return templates.TemplateResponse(
        "admin/media_settings.html",
        {
            "request": request,
            "user": current_user,
            "media_settings": media_settings,
            "settings_schema": settings_schema,
            "admin_path": get_request_admin_path(request),
        },
    )


@router.post(f"{ADMIN_PATH}/api/v1/media/settings")
async def update_media_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = await request.form()
    csrf_token = _form_text(form, "csrf_token", "")
    verify_csrf_token(request, csrf_token)

    settings_to_update: Dict[str, Any] = {
        "media_image_quality": _form_int(form, "media_image_quality", 85),
        "media_max_image_size": _form_int(form, "media_max_image_size", 2048),
        "media_auto_compress": _form_bool(form, "media_auto_compress", False),
        "media_max_file_size": _form_int(form, "media_max_file_size", 52428800),
        "media_allowed_image_formats": _normalize_csv_text(
            _form_text(form, "media_allowed_image_formats", "jpg,jpeg,png,gif,bmp,webp,tiff")
        ),
        "media_allowed_video_formats": _normalize_csv_text(
            _form_text(form, "media_allowed_video_formats", "mp4,avi,mov,wmv,flv,webm,mkv")
        ),
        "media_allowed_audio_formats": _normalize_csv_text(
            _form_text(form, "media_allowed_audio_formats", "mp3,wav,flac,aac,ogg,m4a")
        ),
        "media_allowed_document_formats": _normalize_csv_text(
            _form_text(form, "media_allowed_document_formats", "pdf,doc,docx,txt,md")
        ),
        "media_extract_exif": _form_bool(form, "media_extract_exif", False),
        "media_remove_exif": _form_bool(form, "media_remove_exif", False),
        "media_enable_watermark": _form_bool(form, "media_enable_watermark", False),
        "media_watermark_text": _form_text(form, "media_watermark_text", DEFAULT_BASE_SETTINGS["site_title"]),
        "media_watermark_opacity": _form_float(form, "media_watermark_opacity", 0.5),
        "media_progressive_jpeg": _form_bool(form, "media_progressive_jpeg", False),
        "media_enable_cdn": _form_bool(form, "media_enable_cdn", False),
        "media_cdn_url": _form_text(form, "media_cdn_url", ""),
        "media_auto_cleanup": _form_bool(form, "media_auto_cleanup", False),
        "media_cleanup_days": _form_int(form, "media_cleanup_days", 30),
        "thumbnail_enabled": _form_bool(form, "thumbnail_enabled", False),
        "thumbnail_cache_dir": _form_text(form, "thumbnail_cache_dir", "media_uploads/_variant_cache"),
        "thumbnail_allowed_dpr": _normalize_csv_text(_form_text(form, "thumbnail_allowed_dpr", "1,2")),
        "thumbnail_allowed_fmt": _normalize_csv_text(
            _form_text(form, "thumbnail_allowed_fmt", "auto,avif,webp,jpg,png")
        ).lower(),
        "thumbnail_default_fmt": _form_text(form, "thumbnail_default_fmt", "auto").lower(),
        "thumbnail_processor_version": _form_text(form, "thumbnail_processor_version", "v1"),
        "thumbnail_lock_timeout_ms": _form_int(form, "thumbnail_lock_timeout_ms", 15000),
        "thumbnail_negative_cache_ttl_seconds": _form_int(form, "thumbnail_negative_cache_ttl_seconds", 30),
        "thumbnail_generate_timeout_ms": _form_int(form, "thumbnail_generate_timeout_ms", 4000),
        "thumbnail_source_max_megapixels": _form_int(form, "thumbnail_source_max_megapixels", 40),
        "thumbnail_cleanup_interval_hours": _form_int(form, "thumbnail_cleanup_interval_hours", 168),
        "external_image_policy": _form_text(form, "external_image_policy", "passthrough").lower(),
        "external_image_allowlist": _normalize_csv_text(_form_text(form, "external_image_allowlist", "")),
        "external_image_max_bytes": _form_int(form, "external_image_max_bytes", 10485760),
        "external_image_timeout_ms": _form_int(form, "external_image_timeout_ms", 3000),
        "external_image_redirect_limit": _form_int(form, "external_image_redirect_limit", 2),
        "external_image_allowed_mime": _normalize_csv_text(
            _form_text(
                form,
                "external_image_allowed_mime",
                "image/jpeg,image/png,image/webp,image/avif,image/gif",
            )
        ).lower(),
        "external_image_localize_concurrency": _form_int(form, "external_image_localize_concurrency", 2),
        "external_image_localize_max_retries": _form_int(form, "external_image_localize_max_retries", 2),
    }

    errors = []

    if settings_to_update["media_image_quality"] < 1 or settings_to_update["media_image_quality"] > 100:
        errors.append("图像压缩质量必须在 1 到 100 之间")
    if settings_to_update["media_max_image_size"] < 500 or settings_to_update["media_max_image_size"] > 12000:
        errors.append("图像最大尺寸必须在 500 到 12000 之间")
    if settings_to_update["media_max_file_size"] < 1024 * 1024:
        errors.append("文件大小限制不能小于 1MB")
    if settings_to_update["media_max_file_size"] > 500 * 1024 * 1024:
        errors.append("文件大小限制不能超过 500MB")
    if settings_to_update["media_watermark_opacity"] < 0.0 or settings_to_update["media_watermark_opacity"] > 1.0:
        errors.append("水印透明度必须在 0.0 到 1.0 之间")
    if settings_to_update["media_cleanup_days"] < 1 or settings_to_update["media_cleanup_days"] > 365:
        errors.append("清理天数必须在 1 到 365 之间")

    image_formats = [fmt for fmt in settings_to_update["media_allowed_image_formats"].split(",") if fmt]
    if not image_formats:
        errors.append("至少需要允许一种图像格式")

    allowed_dpr_raw = [part.strip() for part in settings_to_update["thumbnail_allowed_dpr"].split(",") if part.strip()]
    allowed_dpr_values = []
    for part in allowed_dpr_raw:
        try:
            value = int(part)
        except ValueError:
            errors.append("thumbnail_allowed_dpr 仅允许整数值")
            continue
        if value not in {1, 2}:
            errors.append("thumbnail_allowed_dpr 仅允许 1 和 2")
            continue
        allowed_dpr_values.append(value)
    allowed_dpr_values = sorted(set(allowed_dpr_values))
    if not allowed_dpr_values:
        errors.append("thumbnail_allowed_dpr 不能为空")
    settings_to_update["thumbnail_allowed_dpr"] = ",".join(str(v) for v in allowed_dpr_values)

    allowed_fmt_set = {"auto", "avif", "webp", "jpg", "png"}
    allowed_fmt_raw = [part.strip().lower() for part in settings_to_update["thumbnail_allowed_fmt"].split(",") if part.strip()]
    if not allowed_fmt_raw:
        errors.append("thumbnail_allowed_fmt 不能为空")
    if any(fmt not in allowed_fmt_set for fmt in allowed_fmt_raw):
        errors.append("thumbnail_allowed_fmt 包含不支持的格式")
    if "auto" not in allowed_fmt_raw:
        errors.append("thumbnail_allowed_fmt 必须包含 auto")
    if settings_to_update["thumbnail_default_fmt"] not in allowed_fmt_set:
        errors.append("thumbnail_default_fmt 不合法")
    if settings_to_update["thumbnail_default_fmt"] not in allowed_fmt_raw:
        errors.append("thumbnail_default_fmt 必须属于 thumbnail_allowed_fmt")
    settings_to_update["thumbnail_allowed_fmt"] = ",".join(sorted(set(allowed_fmt_raw), key=allowed_fmt_raw.index))

    if settings_to_update["thumbnail_lock_timeout_ms"] < 1000 or settings_to_update["thumbnail_lock_timeout_ms"] > 60000:
        errors.append("thumbnail_lock_timeout_ms 必须在 1000 到 60000 之间")
    if (
        settings_to_update["thumbnail_negative_cache_ttl_seconds"] < 1
        or settings_to_update["thumbnail_negative_cache_ttl_seconds"] > 600
    ):
        errors.append("thumbnail_negative_cache_ttl_seconds 必须在 1 到 600 之间")
    if settings_to_update["thumbnail_generate_timeout_ms"] < 500 or settings_to_update["thumbnail_generate_timeout_ms"] > 30000:
        errors.append("thumbnail_generate_timeout_ms 必须在 500 到 30000 之间")
    if (
        settings_to_update["thumbnail_source_max_megapixels"] < 1
        or settings_to_update["thumbnail_source_max_megapixels"] > 200
    ):
        errors.append("thumbnail_source_max_megapixels 必须在 1 到 200 之间")
    if (
        settings_to_update["thumbnail_cleanup_interval_hours"] < 1
        or settings_to_update["thumbnail_cleanup_interval_hours"] > 24 * 365
    ):
        errors.append("thumbnail_cleanup_interval_hours 必须在 1 到 8760 之间")

    if settings_to_update["external_image_policy"] not in {"passthrough", "localize_async", "block"}:
        errors.append("external_image_policy 仅支持 passthrough、localize_async、block")
    if settings_to_update["external_image_max_bytes"] < 1024 * 1024:
        errors.append("external_image_max_bytes 不能小于 1MB")
    if settings_to_update["external_image_max_bytes"] > 100 * 1024 * 1024:
        errors.append("external_image_max_bytes 不能超过 100MB")
    if settings_to_update["external_image_timeout_ms"] < 500 or settings_to_update["external_image_timeout_ms"] > 30000:
        errors.append("external_image_timeout_ms 必须在 500 到 30000 之间")
    if settings_to_update["external_image_redirect_limit"] < 0 or settings_to_update["external_image_redirect_limit"] > 5:
        errors.append("external_image_redirect_limit 必须在 0 到 5 之间")
    if (
        settings_to_update["external_image_localize_concurrency"] < 1
        or settings_to_update["external_image_localize_concurrency"] > 16
    ):
        errors.append("external_image_localize_concurrency 必须在 1 到 16 之间")
    if (
        settings_to_update["external_image_localize_max_retries"] < 0
        or settings_to_update["external_image_localize_max_retries"] > 10
    ):
        errors.append("external_image_localize_max_retries 必须在 0 到 10 之间")

    allowed_mime_values = [
        item.strip().lower() for item in settings_to_update["external_image_allowed_mime"].split(",") if item.strip()
    ]
    if not allowed_mime_values:
        errors.append("external_image_allowed_mime 不能为空")
    if any(not mime.startswith("image/") for mime in allowed_mime_values):
        errors.append("external_image_allowed_mime 仅允许 image/* 类型")
    settings_to_update["external_image_allowed_mime"] = ",".join(sorted(set(allowed_mime_values), key=allowed_mime_values.index))

    if errors:
        return JSONResponse(
            {"success": False, "error": "配置验证失败", "details": errors},
            status_code=400,
        )

    try:
        for key, value in settings_to_update.items():
            current = crud_setting.get_setting(db, key)
            if current:
                setting_update = SettingUpdate(value={"value": value}, category="media", type=_get_setting_type(value))
                crud_setting.update_setting(db, key, setting_update)
            else:
                setting_create = SettingCreate(
                    key=key,
                    value={"value": value},
                    description=f"媒体设置: {key}",
                    category="media",
                    type=_get_setting_type(value),
                )
                crud_setting.create_setting(db, setting_create)
        return JSONResponse(
            {
                "success": True,
                "message": "媒体设置已更新",
                "redirect_url": f"{get_request_admin_path(request)}/media/settings",
            }
        )
    except Exception as exc:
        return JSONResponse({"success": False, "error": f"保存设置失败: {exc}"}, status_code=500)


@router.get(f"{ADMIN_PATH}/api/v1/media/settings/current")
async def get_current_media_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        media_settings = {}
        all_settings = crud_setting.get_settings_by_category(db, "media")
        for setting in all_settings:
            media_settings[setting.key] = setting.value.get("value") if setting.value else None
        return JSONResponse({"success": True, "settings": media_settings})
    except Exception as exc:
        return JSONResponse({"success": False, "error": f"获取设置失败: {exc}"}, status_code=500)
