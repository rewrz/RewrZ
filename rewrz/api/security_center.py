"""
后台安全中心页面逻辑
"""
from __future__ import annotations

from math import ceil

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.admin_path import get_request_admin_path
from ..core.admin_security import (
    DEFAULT_COMMENT_RATE_LIMIT_PER_MIN,
    DEFAULT_LOGIN_AUDIT_RETENTION_DAYS,
    DEFAULT_LOGIN_BAN_MINUTES,
    DEFAULT_LOGIN_MAX_ATTEMPTS,
    DEFAULT_NEW_IP_ALERT_ENABLED,
    clear_login_attempts,
    count_login_attempts,
    get_login_attempts_paginated,
    get_login_security_config,
    mark_login_audit_cleanup_run,
    prune_login_audit_log,
    save_security_config,
    truncate_login_audit_log,
)
from ..core.security import verify_csrf_token
from ..core.template_filters import get_templates
from ..schemas import User


templates = get_templates()
LOGIN_AUDIT_ALLOWED_PAGE_SIZES = [20, 50, 100]
LOGIN_AUDIT_DEFAULT_PAGE_SIZE = 20


def _render_security_center(
    request: Request,
    *,
    user: User,
    db: Session,
    message: str | None = None,
) -> HTMLResponse:
    config = get_login_security_config(db)
    page = max(1, int(request.query_params.get("page", 1) or 1))
    try:
        page_size = int(request.query_params.get("page_size", LOGIN_AUDIT_DEFAULT_PAGE_SIZE) or LOGIN_AUDIT_DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        page_size = LOGIN_AUDIT_DEFAULT_PAGE_SIZE
    if page_size not in LOGIN_AUDIT_ALLOWED_PAGE_SIZES:
        page_size = LOGIN_AUDIT_DEFAULT_PAGE_SIZE

    filtered_total = count_login_attempts(db)
    total_pages = max(1, ceil(filtered_total / page_size)) if filtered_total else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size
    attempts = get_login_attempts_paginated(db, skip=offset, limit=page_size)

    def _build_page_url(target_page: int) -> str:
        return str(request.url.replace_query_params(page=target_page, page_size=page_size))

    page_window_start = max(1, page - 2)
    page_window_end = min(total_pages, page_window_start + 4)
    page_window_start = max(1, page_window_end - 4)
    page_numbers = list(range(page_window_start, page_window_end + 1))

    pagination = {
        "current_page": page,
        "page_size": page_size,
        "allowed_page_sizes": LOGIN_AUDIT_ALLOWED_PAGE_SIZES,
        "total_pages": total_pages,
        "filtered_total": filtered_total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": _build_page_url(page - 1) if page > 1 else None,
        "next_url": _build_page_url(page + 1) if page < total_pages else None,
        "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
    }
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
                "login_audit_auto_cleanup_enabled": bool(
                    config.get("login_audit_auto_cleanup_enabled", False)
                ),
                "login_audit_retention_days": int(
                    config.get("login_audit_retention_days", DEFAULT_LOGIN_AUDIT_RETENTION_DAYS)
                ),
            },
            "recent_attempts": attempts,
            "audit_pagination": pagination,
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
    login_audit_auto_cleanup_enabled: bool = Form(False),
    login_audit_retention_days: int = Form(DEFAULT_LOGIN_AUDIT_RETENTION_DAYS),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    verify_csrf_token(request, csrf_token)

    if login_max_attempts < 1 or login_max_attempts > 20:
        raise HTTPException(status_code=400, detail="登录失败次数限制必须在 1-20 之间")
    if login_ban_minutes < 1 or login_ban_minutes > 1440:
        raise HTTPException(status_code=400, detail="IP封禁时长必须在 1-1440 分钟之间")
    if comment_rate_limit_per_min < 1 or comment_rate_limit_per_min > 300:
        raise HTTPException(status_code=400, detail="评论API限流必须在 1-300 之间")
    if login_audit_retention_days < 1 or login_audit_retention_days > 3650:
        raise HTTPException(status_code=400, detail="登录审计保留天数必须在 1-3650 之间")

    save_security_config(
        db,
        login_max_attempts=login_max_attempts,
        login_ban_minutes=login_ban_minutes,
        new_ip_login_alert_enabled=new_ip_login_alert_enabled,
        comment_rate_limit_per_min=comment_rate_limit_per_min,
        login_audit_auto_cleanup_enabled=login_audit_auto_cleanup_enabled,
        login_audit_retention_days=login_audit_retention_days,
    )
    return _render_security_center(
        request,
        user=current_user,
        db=db,
        message="安全中心设置已保存",
    )


async def clear_security_audit_logs(
    request: Request,
    db: Session,
    current_user: User,
    *,
    clear_mode: str,
    csrf_token: str,
) -> HTMLResponse:
    verify_csrf_token(request, csrf_token)

    normalized_mode = str(clear_mode or "").strip().lower()
    if normalized_mode == "all":
        deleted_count = clear_login_attempts(db)
        truncate_login_audit_log()
        mark_login_audit_cleanup_run(db)
        message = f"登录审计已全部清空，共删除 {deleted_count} 条数据库记录。"
    elif normalized_mode == "expired":
        retention_days = int(
            get_login_security_config(db).get(
                "login_audit_retention_days",
                DEFAULT_LOGIN_AUDIT_RETENTION_DAYS,
            )
        )
        deleted_count = clear_login_attempts(db, older_than_days=retention_days)
        prune_login_audit_log(older_than_days=retention_days)
        mark_login_audit_cleanup_run(db)
        message = f"已清理超过 {retention_days} 天的登录审计，共删除 {deleted_count} 条数据库记录。"
    else:
        raise HTTPException(status_code=400, detail="不支持的清理方式")

    return _render_security_center(
        request,
        user=current_user,
        db=db,
        message=message,
    )
