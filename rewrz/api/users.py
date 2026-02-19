"""
后台用户资料管理页面逻辑。

当前以“当前登录用户”的个人资料维护为主：
- 基础资料（用户名、邮箱、显示名、简介、网站）
- 头像策略（auto/enabled/disabled）
- 站点资料卡封面（聚合页头部使用）
"""

from typing import Optional, Dict, Any

from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.security import verify_csrf_token
from ..core.template_filters import get_templates
from ..core.avatar import get_avatar_service
from ..crud import user as crud_user
from ..crud import setting as crud_setting
from ..schemas import User, SettingCreate, SettingUpdate


templates = get_templates()

PROFILE_SETTINGS_DEFAULTS = {
    "creator_profile_cover_url": "",
    "creator_profile_micro_cover_url": "",
    "creator_profile_poem_cover_url": "",
    "creator_profile_headline": "",
    "creator_profile_article_bio": "",
    "creator_profile_micro_bio": "",
    "creator_profile_poem_bio": "",
    "creator_profile_location": "",
    "creator_profile_motto": "",
}
ALLOWED_GRAVATAR_MODES = {"auto", "enabled", "disabled"}


def _get_setting_value(db: Session, key: str, default: Any = None) -> Any:
    setting = crud_setting.get_setting(db, key=key)
    if setting and isinstance(setting.value, dict) and "value" in setting.value:
        return setting.value["value"]
    return default


def _upsert_setting_value(db: Session, key: str, value: Any, description: str) -> None:
    payload = {"value": value}
    db_setting = crud_setting.get_setting(db, key=key)
    if db_setting:
        crud_setting.update_setting(db, key=key, setting_update=SettingUpdate(value=payload))
    else:
        crud_setting.create_setting(
            db,
            setting=SettingCreate(key=key, value=payload, description=description),
        )


def _get_profile_settings(db: Session) -> Dict[str, str]:
    profile_settings: Dict[str, str] = {}
    for key, default_value in PROFILE_SETTINGS_DEFAULTS.items():
        value = _get_setting_value(db, key, default_value)
        profile_settings[key] = str(value or "").strip()
    return profile_settings


def _normalize_website_url(raw_value: Optional[str]) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _resolve_profile_avatar_data(db: Session, user_obj) -> Dict[str, Any]:
    avatar_service = get_avatar_service(db)
    final_avatar_url = avatar_service.get_avatar_url(
        email=str(getattr(user_obj, "email", "") or ""),
        user_id=getattr(user_obj, "id", None),
        size=128,
    )
    gravatar_url = avatar_service.get_gravatar_url(
        str(getattr(user_obj, "email", "") or ""),
        size=128,
    )
    custom_avatar_url = str(getattr(user_obj, "avatar_url", "") or "").strip()

    avatar_source = "default"
    if custom_avatar_url:
        avatar_source = "custom"
    elif gravatar_url and gravatar_url == final_avatar_url:
        avatar_source = "gravatar"

    return {
        "avatar_url": final_avatar_url or "/static/images/default-avatar.png",
        "custom_avatar_url": custom_avatar_url,
        "gravatar_url": gravatar_url,
        "avatar_source": avatar_source,
    }


def _build_profile_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    message: str = "",
    error: str = "",
) -> Dict[str, Any]:
    db_user = crud_user.get_user(db, user_id=current_user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    avatar_data = _resolve_profile_avatar_data(db, db_user)
    profile_settings = _get_profile_settings(db)

    return {
        "request": request,
        "user": db_user,
        "profile_user": db_user,
        "profile_settings": profile_settings,
        "profile_message": message,
        "profile_error": error,
        "admin_path": getattr(request.state, "admin_path", "/admin"),
        **avatar_data,
    }


async def admin_users_page(
    request: Request,
    db: Session,
    current_user: User,
) -> HTMLResponse:
    context = _build_profile_context(request, db, current_user)
    return templates.TemplateResponse("admin/users.html", context)


async def update_admin_user_profile(
    request: Request,
    db: Session,
    current_user: User,
    username: str = Form(...),
    email: str = Form(...),
    display_name: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    use_gravatar: str = Form("auto"),
    creator_profile_cover_url: Optional[str] = Form(None),
    creator_profile_micro_cover_url: Optional[str] = Form(None),
    creator_profile_poem_cover_url: Optional[str] = Form(None),
    creator_profile_headline: Optional[str] = Form(None),
    creator_profile_article_bio: Optional[str] = Form(None),
    creator_profile_micro_bio: Optional[str] = Form(None),
    creator_profile_poem_bio: Optional[str] = Form(None),
    creator_profile_location: Optional[str] = Form(None),
    creator_profile_motto: Optional[str] = Form(None),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    verify_csrf_token(request, csrf_token)

    db_user = crud_user.get_user(db, user_id=current_user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    normalized_username = str(username or "").strip()
    normalized_email = str(email or "").strip().lower()
    normalized_use_gravatar = str(use_gravatar or "auto").strip().lower()
    normalized_website = _normalize_website_url(website)

    if not normalized_username:
        context = _build_profile_context(request, db, current_user, error="用户名不能为空。")
        return templates.TemplateResponse("admin/users.html", context, status_code=400)
    if not normalized_email:
        context = _build_profile_context(request, db, current_user, error="邮箱不能为空。")
        return templates.TemplateResponse("admin/users.html", context, status_code=400)
    if normalized_use_gravatar not in ALLOWED_GRAVATAR_MODES:
        normalized_use_gravatar = "auto"

    existing_user = crud_user.get_user_by_username(db, normalized_username)
    if existing_user and existing_user.id != db_user.id:
        context = _build_profile_context(request, db, current_user, error="用户名已被占用。")
        return templates.TemplateResponse("admin/users.html", context, status_code=400)

    existing_email = crud_user.get_user_by_email(db, normalized_email)
    if existing_email and existing_email.id != db_user.id:
        context = _build_profile_context(request, db, current_user, error="邮箱已被占用。")
        return templates.TemplateResponse("admin/users.html", context, status_code=400)

    db_user.username = normalized_username
    db_user.email = normalized_email
    db_user.display_name = str(display_name or "").strip() or None
    db_user.bio = str(bio or "").strip() or None
    db_user.website = normalized_website or None
    db_user.use_gravatar = normalized_use_gravatar
    db.commit()
    db.refresh(db_user)

    profile_updates = {
        "creator_profile_cover_url": creator_profile_cover_url,
        "creator_profile_micro_cover_url": creator_profile_micro_cover_url,
        "creator_profile_poem_cover_url": creator_profile_poem_cover_url,
        "creator_profile_headline": creator_profile_headline,
        "creator_profile_article_bio": creator_profile_article_bio,
        "creator_profile_micro_bio": creator_profile_micro_bio,
        "creator_profile_poem_bio": creator_profile_poem_bio,
        "creator_profile_location": creator_profile_location,
        "creator_profile_motto": creator_profile_motto,
    }
    for setting_key, raw_value in profile_updates.items():
        _upsert_setting_value(
            db,
            setting_key,
            str(raw_value or "").strip(),
            "Creator profile setting",
        )

    context = _build_profile_context(
        request,
        db,
        current_user,
        message="个人资料已更新。",
    )
    return templates.TemplateResponse("admin/users.html", context)
