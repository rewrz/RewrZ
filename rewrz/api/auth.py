import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.admin_path import get_admin_path
from ..core.config import settings
from ..core.template_filters import get_templates
from ..core.security import (
    verify_password,
    create_access_token,
    get_current_user,
    decode_access_token,
    is_user_token_payload_valid,
    should_use_secure_cookie,
    verify_csrf_token,
    get_password_hash,
)
from ..core.public_alias import resolve_public_display_name
from ..core.admin_security import (
    get_admin_email,
    get_client_ip,
    get_ip_lock_state,
    get_login_security_config,
    is_new_ip_for_user,
    record_login_attempt,
    remember_user_ip,
)
from ..core.notification_email import (
    is_email_delivery_configured,
    send_new_ip_login_alert,
    send_password_reset_email,
    write_password_reset_debug_delivery,
)
from ..crud import user as crud_user
from ..schemas import User

router = APIRouter()
templates = get_templates()

PASSWORD_RESET_EXPIRE_MINUTES = 30
PASSWORD_RESET_REQUEST_INTERVAL_SECONDS = 60


def _hash_password_reset_token(raw_token: str) -> str:
    payload = f"{str(settings.SECRET_KEY)}:{str(raw_token or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_password_reset_url(request: Request, raw_token: str) -> str:
    admin_path = get_admin_path()
    query = urlencode({"token": raw_token})
    return str(request.url_for("dynamic_admin_reset_password_page")) + f"?{query}"


def _build_password_reset_delivery_note() -> str:
    if is_email_delivery_configured():
        return "如果账户存在且邮箱可用，系统已发送密码重置链接。"
    return "当前环境未配置邮件服务。若账户存在，系统已将重置链接写入本地调试投递记录。"


def _normalize_utc_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_password_reset_user(db: Session, identifier: str):
    normalized_identifier = str(identifier or "").strip()
    if not normalized_identifier:
        return None
    lowered_identifier = normalized_identifier.lower()
    return (
        db.query(crud_user.User)
        .filter(
            or_(
                crud_user.User.username == normalized_identifier,
                crud_user.User.email == lowered_identifier,
            )
        )
        .first()
    )


def _render_password_reset_request_page(
    request: Request,
    *,
    admin_path: str,
    error_message: str | None = None,
    success_message: str | None = None,
    delivery_note: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "admin/forgot_password.html",
        {
            "request": request,
            "admin_path": admin_path,
            "error_message": error_message,
            "success_message": success_message,
            "delivery_note": delivery_note,
        },
        status_code=status_code,
    )


def _render_password_reset_form_page(
    request: Request,
    *,
    admin_path: str,
    token: str,
    error_message: str | None = None,
    success_message: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "admin/reset_password.html",
        {
            "request": request,
            "admin_path": admin_path,
            "token": token,
            "error_message": error_message,
            "success_message": success_message,
        },
        status_code=status_code,
    )


def forgot_password_page(request: Request):
    admin_path = get_admin_path()
    return _render_password_reset_request_page(request, admin_path=admin_path)


def submit_forgot_password(
    request: Request,
    db: Session,
    *,
    identifier: str,
    csrf_token: str,
    background_tasks: BackgroundTasks | None = None,
):
    verify_csrf_token(request, csrf_token)

    admin_path = get_admin_path()
    normalized_identifier = str(identifier or "").strip()
    if not normalized_identifier:
        return _render_password_reset_request_page(
            request,
            admin_path=admin_path,
            error_message="请输入用户名或邮箱。",
            status_code=400,
        )

    user = _resolve_password_reset_user(db, normalized_identifier)
    delivery_note = _build_password_reset_delivery_note()
    now = datetime.now(timezone.utc)

    if user is not None and bool(getattr(user, "is_active", False)) and str(getattr(user, "email", "") or "").strip():
        last_sent_at = _normalize_utc_datetime(getattr(user, "password_reset_sent_at", None))
        if last_sent_at is None or (now - last_sent_at).total_seconds() >= PASSWORD_RESET_REQUEST_INTERVAL_SECONDS:
            raw_token = secrets.token_urlsafe(32)
            expires_at = now + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
            token_hash = _hash_password_reset_token(raw_token)
            crud_user.set_password_reset_token(
                db,
                int(user.id),
                token_hash=token_hash,
                sent_at=now,
                expires_at=expires_at,
            )
            reset_url = _build_password_reset_url(request, raw_token)
            if is_email_delivery_configured():
                if background_tasks is not None:
                    background_tasks.add_task(
                        send_password_reset_email,
                        str(user.email),
                        username=str(user.username),
                        reset_url=reset_url,
                        expire_minutes=PASSWORD_RESET_EXPIRE_MINUTES,
                    )
                else:
                    send_password_reset_email(
                        str(user.email),
                        username=str(user.username),
                        reset_url=reset_url,
                        expire_minutes=PASSWORD_RESET_EXPIRE_MINUTES,
                    )
            else:
                write_password_reset_debug_delivery(
                    username=str(user.username),
                    email=str(user.email),
                    reset_url=reset_url,
                    expires_at=expires_at,
                )

    return _render_password_reset_request_page(
        request,
        admin_path=admin_path,
        success_message="请求已受理，请检查邮箱或调试投递记录。",
        delivery_note=delivery_note,
    )


def reset_password_page(request: Request, db: Session, *, token: str):
    admin_path = get_admin_path()
    raw_token = str(token or "").strip()
    if not raw_token:
        return _render_password_reset_form_page(
            request,
            admin_path=admin_path,
            token="",
            error_message="重置链接缺少令牌，请重新发起找回密码。",
            status_code=400,
        )

    token_hash = _hash_password_reset_token(raw_token)
    user = crud_user.get_user_by_password_reset_token_hash(db, token_hash)
    expires_at = _normalize_utc_datetime(getattr(user, "password_reset_expires_at", None)) if user else None
    if user is None or expires_at is None or expires_at <= datetime.now(timezone.utc):
        return _render_password_reset_form_page(
            request,
            admin_path=admin_path,
            token="",
            error_message="重置链接无效或已过期，请重新发起找回密码。",
            status_code=400,
        )

    return _render_password_reset_form_page(
        request,
        admin_path=admin_path,
        token=raw_token,
    )


def submit_reset_password(
    request: Request,
    db: Session,
    *,
    token: str,
    password: str,
    password_confirm: str,
    csrf_token: str,
):
    verify_csrf_token(request, csrf_token)

    admin_path = get_admin_path()
    raw_token = str(token or "").strip()
    new_password = str(password or "")
    confirm_password = str(password_confirm or "")

    if len(new_password) < 8:
        return _render_password_reset_form_page(
            request,
            admin_path=admin_path,
            token=raw_token,
            error_message="新密码至少需要 8 位。",
            status_code=400,
        )

    if new_password != confirm_password:
        return _render_password_reset_form_page(
            request,
            admin_path=admin_path,
            token=raw_token,
            error_message="两次输入的密码不一致。",
            status_code=400,
        )

    token_hash = _hash_password_reset_token(raw_token)
    user = crud_user.get_user_by_password_reset_token_hash(db, token_hash)
    expires_at = _normalize_utc_datetime(getattr(user, "password_reset_expires_at", None)) if user else None
    if user is None or expires_at is None or expires_at <= datetime.now(timezone.utc):
        return _render_password_reset_form_page(
            request,
            admin_path=admin_path,
            token="",
            error_message="重置链接无效或已过期，请重新发起找回密码。",
            status_code=400,
        )

    user.hashed_password = get_password_hash(new_password)
    user.password_reset_token_hash = None
    user.password_reset_sent_at = None
    user.password_reset_expires_at = None
    current_version = int(getattr(user, "token_version", 1) or 1)
    user.token_version = current_version + 1
    db.commit()

    response = RedirectResponse(
        url=f"{admin_path}/login?reset=success",
        status_code=303,
    )
    response.delete_cookie("access_token", path="/")
    return response


def _resolve_optional_authenticated_user(request: Request, db: Session):
    """解析当前请求中的登录用户，不抛异常，失败时返回 None。"""
    token = (request.cookies.get("access_token") or "").strip()
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    raw_user_id = payload.get("sub")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    db_user = crud_user.get_user(db, user_id=user_id)
    if not is_user_token_payload_valid(db_user, payload):
        return None
    return db_user

# 登录端点已移至main.py中的动态路由注册系统以确保安全性
# @router.post("/token")
# async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
# 登录函数实现已移至main.py中的动态路由注册系统
# async def login_for_access_token_impl(response: Response, form_data: OAuth2PasswordRequestForm, db: Session):
#     user = crud_user.get_user_by_username(db, username=form_data.username)
#     if not user or not verify_password(form_data.password, user.hashed_password):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         data={"sub": str(user.id)}, expires_delta=access_token_expires
#     )
#     response.set_cookie(key="access_token", value=access_token, httponly=True, expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite='Lax')
#     admin_path = get_admin_path()
#     response.headers["HX-Redirect"] = f"{admin_path}/dashboard"
#     return {"message": "Login successful"}

# 登录功能实现（供动态路由调用）
async def login_for_access_token_impl(
    response: Response,
    form_data: OAuth2PasswordRequestForm,
    db: Session,
    request: Request,
    background_tasks: BackgroundTasks | None = None,
):
    """
    登录函数实现，供动态路由调用
    """
    username = (form_data.username or "").strip()
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    security_cfg = get_login_security_config(db)
    max_attempts = int(security_cfg.get("login_max_attempts", 3))
    ban_minutes = int(security_cfg.get("login_ban_minutes", 15))

    blocked, remaining_seconds, _ = get_ip_lock_state(
        db,
        ip_address=ip_address,
        max_attempts=max_attempts,
        ban_minutes=ban_minutes,
    )
    if blocked:
        record_login_attempt(
            db,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            reason=f"blocked:{remaining_seconds}s",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过多，IP已临时封禁。请在约 {max(1, remaining_seconds // 60)} 分钟后重试。",
        )

    user = crud_user.get_user_by_username(db, username=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        record_login_attempt(
            db,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            reason="bad_credentials",
        )

        blocked_after_fail, remaining_after_fail, fail_count = get_ip_lock_state(
            db,
            ip_address=ip_address,
            max_attempts=max_attempts,
            ban_minutes=ban_minutes,
        )
        if blocked_after_fail or fail_count >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"连续登录失败次数达到上限，IP已封禁 {ban_minutes} 分钟。",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_time = datetime.now(timezone.utc)
    user.last_login_at = login_time
    db.commit()

    # 成功登录审计
    record_login_attempt(
        db,
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        reason="login_success",
    )

    # 新IP登录告警（可配置）
    alert_enabled = bool(security_cfg.get("new_ip_login_alert_enabled", False))
    is_new_ip = is_new_ip_for_user(db, username=username, ip_address=ip_address)
    if is_new_ip:
        remember_user_ip(db, username=username, ip_address=ip_address)

    if alert_enabled and is_new_ip:
        admin_email = get_admin_email(db)
        if admin_email:
            time_text = login_time.strftime("%Y-%m-%d %H:%M:%S UTC")
            if background_tasks is not None:
                background_tasks.add_task(
                    send_new_ip_login_alert,
                    admin_email,
                    username,
                    ip_address,
                    user_agent,
                    time_text,
                )
            else:
                send_new_ip_login_alert(
                    admin_email,
                    username,
                    ip_address,
                    user_agent,
                    time_text,
                )

    access_token_expires = timedelta(minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "token_version": int(getattr(user, "token_version", 1) or 1),
        },
        expires_delta=access_token_expires,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        expires=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
        samesite="lax",
        secure=should_use_secure_cookie(request),
    )
    admin_path = get_admin_path()
    response.headers["HX-Redirect"] = f"{admin_path}/dashboard"
    # 返回空内容，只设置头部信息
    return {"message": "Login successful"}


@router.get("/api/v1/auth/status")
@router.get("/api/auth/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """前台登录态探针，不返回后台路径。"""
    current_user = _resolve_optional_authenticated_user(request, db)
    if current_user is None:
        return {
            "logged_in": False,
            "user": None,
        }

    display_name = resolve_public_display_name(
        getattr(current_user, "display_name", None),
        seed_value=getattr(current_user, "id", None),
        fallback="已登录用户",
    )
    return {
        "logged_in": True,
        "user": {
            "id": int(getattr(current_user, "id", 0) or 0),
            "username": (getattr(current_user, "username", "") or "").strip(),
            "display_name": display_name,
        },
    }


@router.get("/auth/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token", path="/")
    request.session.pop("csrf_token", None)
    return response

@router.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# 后台登录和仪表盘路由已完全移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性
