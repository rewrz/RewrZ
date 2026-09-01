"""
后台用户管理页面逻辑。

当前保持轻量实现：
- 当前登录用户的个人资料维护
- 用户列表
- 启用/停用
- 角色切换
- 密码重置
"""

from math import ceil
from typing import Optional, Dict, Any
import json

from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.admin_path import get_request_admin_path
from ..core.admin_security import get_admin_user_activity_map, get_client_ip, record_admin_user_action
from ..core.admin_security import ADMIN_ROLE_LABELS
from ..core.security import ensure_admin_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..core.avatar import get_avatar_service
from ..core.url_normalizer import normalize_local_asset_url
from ..crud import user as crud_user
from ..crud import setting as crud_setting
from ..schemas import (
    User,
    SettingCreate,
    SettingUpdate,
    UserAdminCreate,
    UserAdminRoleUpdate,
    UserAdminStatusUpdate,
    UserPasswordReset,
)


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
    "micro_mention_links_json": "{}",
}
ALLOWED_GRAVATAR_MODES = {"auto", "enabled", "disabled"}
ALLOWED_ADMIN_ROLES = {"admin", "super_admin"}
MANAGED_USERS_ALLOWED_PAGE_SIZES = [10, 20, 50, 100]
MANAGED_USERS_DEFAULT_PAGE_SIZE = 20


def _get_setting_value(db: Session, key: str, default: Any = None) -> Any:
    setting = crud_setting.get_setting(db, key=key)
    if setting and isinstance(setting.value, dict) and "value" in setting.value:
        return setting.value["value"]
    return default


def _ensure_super_admin_user(current_user: User) -> None:
    role = str(getattr(current_user, "role", "") or "").strip().lower()
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="需要超级管理员权限")


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


def _normalize_micro_mention_links_json(raw_value: Optional[str]) -> str:
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return "{}"

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return "{}"

    if isinstance(parsed, list):
        converted: Dict[str, str] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or item.get("key", "")).strip().lstrip("@")
            link = _normalize_website_url(str(item.get("url", "") or item.get("link", "")).strip())
            if not name or not link:
                continue
            converted[name] = link
        parsed = converted

    if not isinstance(parsed, dict):
        return "{}"

    normalized: Dict[str, str] = {}
    for raw_name, raw_link in parsed.items():
        name = str(raw_name or "").strip().lstrip("@")
        link = _normalize_website_url(str(raw_link or "").strip())
        if not name or not link:
            continue
        normalized[name] = link

    return json.dumps(normalized, ensure_ascii=False)


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
    search_query = str(request.query_params.get("q", "") or "").strip()
    page = max(1, int(request.query_params.get("page", 1) or 1))
    try:
        page_size = int(request.query_params.get("page_size", MANAGED_USERS_DEFAULT_PAGE_SIZE) or MANAGED_USERS_DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        page_size = MANAGED_USERS_DEFAULT_PAGE_SIZE
    if page_size not in MANAGED_USERS_ALLOWED_PAGE_SIZES:
        page_size = MANAGED_USERS_DEFAULT_PAGE_SIZE

    filtered_total = crud_user.count_users(db, search=search_query)
    total_pages = max(1, ceil(filtered_total / page_size)) if filtered_total else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size
    user_rows = crud_user.get_users(db, search=search_query, skip=offset, limit=page_size)
    activity_map = get_admin_user_activity_map(
        db,
        user_ids=[int(getattr(item, "id", 0) or 0) for item in user_rows],
    )

    for managed_user in user_rows:
        activity_payload = activity_map.get(int(getattr(managed_user, "id", 0) or 0), {})
        setattr(managed_user, "admin_recent_activity", activity_payload)

    def _build_page_url(target_page: int) -> str:
        params: Dict[str, str] = {"page": str(target_page), "page_size": str(page_size)}
        if search_query:
            params["q"] = search_query
        return str(request.url.replace_query_params(**params))

    page_window_start = max(1, page - 2)
    page_window_end = min(total_pages, page_window_start + 4)
    page_window_start = max(1, page_window_end - 4)
    page_numbers = list(range(page_window_start, page_window_end + 1))

    pagination = {
        "current_page": page,
        "page_size": page_size,
        "allowed_page_sizes": MANAGED_USERS_ALLOWED_PAGE_SIZES,
        "total_pages": total_pages,
        "filtered_total": filtered_total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": _build_page_url(page - 1) if page > 1 else None,
        "next_url": _build_page_url(page + 1) if page < total_pages else None,
        "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
    }

    return {
        "request": request,
        "user": db_user,
        "profile_user": db_user,
        "managed_users": user_rows,
        "managed_users_search": search_query,
        "profile_settings": profile_settings,
        "profile_message": message,
        "profile_error": error,
        "admin_path": get_request_admin_path(request),
        "allowed_admin_roles": sorted(ALLOWED_ADMIN_ROLES),
        "admin_role_labels": ADMIN_ROLE_LABELS,
        "managed_users_pagination": pagination,
        **avatar_data,
    }


async def admin_users_page(
    request: Request,
    db: Session,
    current_user: User,
) -> HTMLResponse:
    ensure_admin_user(current_user)
    context = _build_profile_context(request, db, current_user)
    return templates.TemplateResponse(request, "admin/users.html", context)


async def create_admin_user_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    username: str,
    email: str,
    password: str,
    role: str,
    display_name: Optional[str],
    csrf_token: str,
):
    ensure_admin_user(current_user)
    _ensure_super_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    payload = UserAdminCreate(
        username=str(username or "").strip(),
        email=str(email or "").strip().lower(),
        password=password,
        role=str(role or "admin").strip().lower(),
        display_name=str(display_name or "").strip() or None,
    )

    if payload.role not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="角色不合法")

    if crud_user.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="用户名已被占用")
    if crud_user.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="邮箱已被占用")

    created = crud_user.create_admin_user(
        db,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        display_name=payload.display_name,
        is_active=True,
    )
    record_admin_user_action(
        db,
        event="created",
        actor_user_id=int(current_user.id),
        actor_username=str(getattr(current_user, "username", "") or ""),
        target_user_id=int(created.id),
        target_username=str(getattr(created, "username", "") or ""),
        ip_address=get_client_ip(request),
        detail={"role": str(getattr(created, "role", "admin") or "admin")},
    )
    return {"success": True, "message": "后台用户已创建", "user_id": int(created.id)}


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
    micro_mention_links_json: Optional[str] = Form(None),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    ensure_admin_user(current_user)
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
        return templates.TemplateResponse(request, "admin/users.html", context, status_code=400)
    if not normalized_email:
        context = _build_profile_context(request, db, current_user, error="邮箱不能为空。")
        return templates.TemplateResponse(request, "admin/users.html", context, status_code=400)
    if normalized_use_gravatar not in ALLOWED_GRAVATAR_MODES:
        normalized_use_gravatar = "auto"

    existing_user = crud_user.get_user_by_username(db, normalized_username)
    if existing_user and existing_user.id != db_user.id:
        context = _build_profile_context(request, db, current_user, error="用户名已被占用。")
        return templates.TemplateResponse(request, "admin/users.html", context, status_code=400)

    existing_email = crud_user.get_user_by_email(db, normalized_email)
    if existing_email and existing_email.id != db_user.id:
        context = _build_profile_context(request, db, current_user, error="邮箱已被占用。")
        return templates.TemplateResponse(request, "admin/users.html", context, status_code=400)

    db_user.username = normalized_username
    db_user.email = normalized_email
    db_user.display_name = str(display_name or "").strip() or None
    db_user.bio = str(bio or "").strip() or None
    db_user.website = normalized_website or None
    db_user.use_gravatar = normalized_use_gravatar
    db.commit()
    db.refresh(db_user)

    profile_updates = {
        "creator_profile_cover_url": normalize_local_asset_url(creator_profile_cover_url),
        "creator_profile_micro_cover_url": normalize_local_asset_url(creator_profile_micro_cover_url),
        "creator_profile_poem_cover_url": normalize_local_asset_url(creator_profile_poem_cover_url),
        "creator_profile_headline": creator_profile_headline,
        "creator_profile_article_bio": creator_profile_article_bio,
        "creator_profile_micro_bio": creator_profile_micro_bio,
        "creator_profile_poem_bio": creator_profile_poem_bio,
        "creator_profile_location": creator_profile_location,
        "creator_profile_motto": creator_profile_motto,
        "micro_mention_links_json": _normalize_micro_mention_links_json(micro_mention_links_json),
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
    return templates.TemplateResponse(request, "admin/users.html", context)


async def update_user_status_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    user_id: int,
    is_active_value: str,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    _ensure_super_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    target_user = crud_user.get_user(db, user_id=user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target_user.id == current_user.id and str(is_active_value).strip().lower() in {"false", "0", "off", "disabled"}:
        raise HTTPException(status_code=400, detail="不能停用当前登录管理员")

    normalized_is_active = str(is_active_value or "").strip().lower() in {"true", "1", "on", "enabled", "active"}
    payload = UserAdminStatusUpdate(is_active=normalized_is_active)
    updated = crud_user.set_user_active_status(db, user_id, is_active=payload.is_active)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    record_admin_user_action(
        db,
        event="status_updated",
        actor_user_id=int(current_user.id),
        actor_username=str(getattr(current_user, "username", "") or ""),
        target_user_id=int(updated.id),
        target_username=str(getattr(updated, "username", "") or ""),
        ip_address=get_client_ip(request),
        detail={"is_active": bool(updated.is_active)},
    )
    return {"success": True, "message": "用户状态已更新"}


async def update_user_role_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    user_id: int,
    role_value: str,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    _ensure_super_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    normalized_role = str(role_value or "").strip().lower()
    if normalized_role not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="角色不合法")

    target_user = crud_user.get_user(db, user_id=user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target_user.id == current_user.id and normalized_role != "super_admin":
        raise HTTPException(status_code=400, detail="不能降级当前登录管理员")

    payload = UserAdminRoleUpdate(role=normalized_role)
    updated = crud_user.set_user_role(db, user_id, role=payload.role)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    record_admin_user_action(
        db,
        event="role_updated",
        actor_user_id=int(current_user.id),
        actor_username=str(getattr(current_user, "username", "") or ""),
        target_user_id=int(updated.id),
        target_username=str(getattr(updated, "username", "") or ""),
        ip_address=get_client_ip(request),
        detail={"role": str(updated.role or "").strip()},
    )
    return {"success": True, "message": "用户角色已更新"}


async def reset_user_password_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    user_id: int,
    password: str,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    _ensure_super_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    target_user = crud_user.get_user(db, user_id=user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    payload = UserPasswordReset(password=password)
    updated = crud_user.reset_user_password(db, user_id, password=payload.password)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    record_admin_user_action(
        db,
        event="password_reset",
        actor_user_id=int(current_user.id),
        actor_username=str(getattr(current_user, "username", "") or ""),
        target_user_id=int(updated.id),
        target_username=str(getattr(updated, "username", "") or ""),
        ip_address=get_client_ip(request),
        detail={},
    )
    return {"success": True, "message": "用户密码已重置"}


async def force_logout_user_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    user_id: int,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    target_user = crud_user.get_user(db, user_id=user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    updated = crud_user.force_logout_user(db, user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    record_admin_user_action(
        db,
        event="force_logout",
        actor_user_id=int(current_user.id),
        actor_username=str(getattr(current_user, "username", "") or ""),
        target_user_id=int(updated.id),
        target_username=str(getattr(updated, "username", "") or ""),
        ip_address=get_client_ip(request),
        detail={"token_version": int(getattr(updated, "token_version", 1) or 1)},
    )
    return {"success": True, "message": "用户现有登录态已失效"}
