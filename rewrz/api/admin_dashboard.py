from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.admin_path import get_admin_path, get_request_admin_path
from ..core.config import settings
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import category as crud_category
from ..crud import comment as crud_comment
from ..crud import post as crud_post
from ..crud import setting as crud_setting
from ..crud import tag as crud_tag
from ..models.login_attempt import LoginAttempt
from ..schemas.setting import SettingCreate, SettingUpdate
from ..schemas import PostCreate, User


router = APIRouter()
templates = get_templates()
SITE_HEALTH_CACHE_KEY = "dashboard_site_health_cache"
SITE_HEALTH_CACHE_TTL_SECONDS = 900


def _collect_stats(db: Session) -> dict:
    return {
        "published_posts": crud_post.count_posts_by_status(db, "published"),
        "draft_posts": crud_post.count_posts_by_status(db, "draft"),
        "total_comments": crud_comment.count_comments(db),
        "pending_comments": crud_comment.count_comments_by_status(db, "pending"),
        "total_categories": crud_category.count_categories(db),
        "total_tags": crud_tag.count_tags(db),
    }


def _safe_media_stats() -> tuple[int, float]:
    media_dir = Path(settings.MEDIA_UPLOAD_DIR)
    if not media_dir.exists() or not media_dir.is_dir():
        return 0, 0.0

    file_count = 0
    total_bytes = 0
    for item in media_dir.rglob("*"):
        if item.is_file():
            file_count += 1
            total_bytes += item.stat().st_size
    total_mb = round(total_bytes / (1024 * 1024), 2)
    return file_count, total_mb


def _load_site_health_cache(db: Session) -> dict | None:
    setting = crud_setting.get_setting(db, SITE_HEALTH_CACHE_KEY)
    if setting is None or not isinstance(setting.value, dict):
        return None
    cached = setting.value.get("value")
    return cached if isinstance(cached, dict) else None


def _save_site_health_cache(db: Session, payload: dict) -> None:
    normalized_payload = {"value": payload}
    existing = crud_setting.get_setting(db, SITE_HEALTH_CACHE_KEY)
    if existing is None:
        crud_setting.create_setting(
            db,
            SettingCreate(
                key=SITE_HEALTH_CACHE_KEY,
                value=normalized_payload,
                description="后台仪表盘健康检查缓存",
                category="system",
                type="json",
            ),
        )
        return

    crud_setting.update_setting(
        db,
        SITE_HEALTH_CACHE_KEY,
        SettingUpdate(
            value=normalized_payload,
            description="后台仪表盘健康检查缓存",
            category="system",
            type="json",
        ),
    )


def _is_site_health_cache_fresh(cached: dict | None, *, now: datetime | None = None) -> bool:
    if not cached:
        return False
    checked_at_iso = str(cached.get("checked_at_iso", "") or "").strip()
    if not checked_at_iso:
        return False
    try:
        checked_at = datetime.fromisoformat(checked_at_iso)
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return (current - checked_at).total_seconds() < SITE_HEALTH_CACHE_TTL_SECONDS


def _collect_site_health(db: Session) -> dict:
    file_count, total_mb = _safe_media_stats()
    pending_comments = crud_comment.count_comments_by_status(db, "pending")

    db_ok = True
    failed_logins_24h = 0
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        failed_logins_24h = (
            db.execute(
                select(LoginAttempt)
                .where(LoginAttempt.success.is_(False), LoginAttempt.created_at >= since)
                .limit(200)
            )
            .scalars()
            .all()
        )
        failed_logins_24h = len(failed_logins_24h)
    except Exception:
        # Avoid breaking dashboard if login_attempts table is not migrated yet.
        db_ok = False

    status = "healthy"
    if pending_comments >= 20 or failed_logins_24h >= 10:
        status = "warning"

    return {
        "status": status,
        "database_ok": db_ok,
        "pending_comments": pending_comments,
        "failed_logins_24h": failed_logins_24h,
        "media_file_count": file_count,
        "media_total_mb": total_mb,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "checked_at_iso": datetime.now(timezone.utc).isoformat(),
        "cache_hit": False,
    }


def get_site_health_snapshot(db: Session) -> dict:
    cached = _load_site_health_cache(db)
    if _is_site_health_cache_fresh(cached):
        return {
            **cached,
            "cache_hit": True,
        }

    health = _collect_site_health(db)
    _save_site_health_cache(db, health)
    return health


async def dashboard_page(request: Request, db: Session, current_user: User):
    recent_comments = crud_comment.get_comments(db, sort_by_latest=True, limit=8)
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "admin_path": request.state.admin_path,
            "recent_comments": recent_comments,
        },
    )


@router.get(f"{get_admin_path()}/api/v1/dashboard/stats")
async def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stats = _collect_stats(db)
    return templates.TemplateResponse(
        request,
        "admin/components/dashboard_stats.html",
        {"request": request, "stats": stats},
    )


@router.get(f"{get_admin_path()}/api/v1/dashboard/site-health")
async def get_site_health(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    health = get_site_health_snapshot(db)
    return templates.TemplateResponse(
        request,
        "admin/components/dashboard_site_health.html",
        {"request": request, "health": health},
    )


@router.post(f"{get_admin_path()}/api/v1/dashboard/quick-draft")
async def create_quick_draft(
    request: Request,
    title: str = Form(""),
    content: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_csrf_token(request, csrf_token)

    normalized_title = (title or "").strip() or f"快速草稿 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    normalized_content = (content or "").strip() or "快速草稿内容..."

    post_create = PostCreate(
        title=normalized_title,
        slug=None,
        content_markdown=normalized_content,
        excerpt=None,
        featured_image_url=None,
        post_type="post",
        status="draft",
        visibility="public",
        password=None,
        allow_comments=True,
        category_ids=[],
        tag_ids=[],
        format_ids=[],
        license_type="cc_by_nc_sa_4",
    )
    created = crud_post.create_post(db, post_create, author_id=current_user.id)
    admin_path = get_request_admin_path(request)

    return JSONResponse(
        {
            "success": True,
            "id": created.id,
            "redirect_url": f"{admin_path}/posts/{created.id}/edit",
        }
    )

