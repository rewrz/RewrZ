"""
后台安全中心页面逻辑
"""
from __future__ import annotations

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.admin_path import get_request_admin_path
from ..core.admin_security import (
    DEFAULT_COMMENT_RATE_LIMIT_PER_MIN,
    DEFAULT_LOGIN_BAN_MINUTES,
    DEFAULT_LOGIN_MAX_ATTEMPTS,
    DEFAULT_NEW_IP_ALERT_ENABLED,
    get_login_security_config,
    get_recent_login_attempts,
    save_security_config,
)
from ..core.security import verify_csrf_token
from ..core.template_filters import get_templates
from ..schemas import User


templates = get_templates()


def _render_security_center(
    request: Request,
    *,
    user: User,
    db: Session,
    message: str | None = None,
) -> HTMLResponse:
    config = get_login_security_config(db)
    attempts = get_recent_login_attempts(db, limit=30)
    return templates.TemplateResponse(
        "admin/security_center.html",
        {
            "request": request,
            "user": user,
            "admin_path": get_request_admin_path(request),
            "message": message,
            "config": {
                "login_max_attempts": config.get(
                    "login_max_attempts", DEFAULT_LOGIN_MAX_ATTEMPTS
                ),
                "login_ban_minutes": config.get("login_ban_minutes", DEFAULT_LOGIN_BAN_MINUTES),
                "new_ip_login_alert_enabled": config.get(
                    "new_ip_login_alert_enabled", DEFAULT_NEW_IP_ALERT_ENABLED
                ),
                "comment_rate_limit_per_min": config.get(
                    "comment_rate_limit_per_min", DEFAULT_COMMENT_RATE_LIMIT_PER_MIN
                ),
            },
            "recent_attempts": attempts,
            "audit_log_path": "data/logs/admin_login_audit.log",
        },
    )


async def security_center_page(request: Request, db: Session, current_user: User) -> HTMLResponse:
    return _render_security_center(request, user=current_user, db=db)


async def update_security_center(
    request: Request,
    db: Session,
    current_user: User,
    login_max_attempts: int = Form(DEFAULT_LOGIN_MAX_ATTEMPTS),
    login_ban_minutes: int = Form(DEFAULT_LOGIN_BAN_MINUTES),
    new_ip_login_alert_enabled: bool = Form(False),
    comment_rate_limit_per_min: int = Form(DEFAULT_COMMENT_RATE_LIMIT_PER_MIN),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    verify_csrf_token(request, csrf_token)

    if login_max_attempts < 1 or login_max_attempts > 20:
        raise HTTPException(status_code=400, detail="登录失败次数限制必须在 1-20 之间")
    if login_ban_minutes < 1 or login_ban_minutes > 1440:
        raise HTTPException(status_code=400, detail="IP封禁时长必须在 1-1440 分钟之间")
    if comment_rate_limit_per_min < 1 or comment_rate_limit_per_min > 300:
        raise HTTPException(status_code=400, detail="评论API限流必须在 1-300 之间")

    save_security_config(
        db,
        login_max_attempts=login_max_attempts,
        login_ban_minutes=login_ban_minutes,
        new_ip_login_alert_enabled=new_ip_login_alert_enabled,
        comment_rate_limit_per_min=comment_rate_limit_per_min,
    )
    return _render_security_center(
        request,
        user=current_user,
        db=db,
        message="安全中心设置已保存",
    )
