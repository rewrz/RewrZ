from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from ..core.database import get_db
from ..core.security import (
    verify_password,
    create_access_token,
    get_current_user,
    decode_access_token,
    should_use_secure_cookie,
)
from ..core.config import settings
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
from ..core.notification_email import send_new_ip_login_alert
from ..crud import user as crud_user
from ..schemas import User

router = APIRouter()


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

    return crud_user.get_user(db, user_id=user_id)

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
#     admin_path = settings.ADMIN_PATH.rstrip('/')
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
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        expires=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
        samesite="lax",
        secure=should_use_secure_cookie(request),
    )
    admin_path = settings.ADMIN_PATH.rstrip('/')
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

@router.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# 后台登录和仪表盘路由已完全移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性
