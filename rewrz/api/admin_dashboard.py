from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token
from ..crud import category as crud_category
from ..crud import comment as crud_comment
from ..crud import post as crud_post
from ..crud import tag as crud_tag
from ..models.login_attempt import LoginAttempt
from ..schemas import PostCreate, User


router = APIRouter()
templates = Jinja2Templates(directory="rewrz/templates")


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


def _collect_site_health(db: Session) -> dict:
    file_count, total_mb = _safe_media_stats()
    pending_comments = crud_comment.count_comments_by_status(db, "pending")

    db_ok = True
    failed_logins_24h = 0
    try:
        since = datetime.utcnow() - timedelta(hours=24)
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
        "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


async def dashboard_page(request: Request, db: Session, current_user: User):
    recent_comments = crud_comment.get_comments(db, sort_by_latest=True, limit=8)
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "admin_path": request.state.admin_path,
            "recent_comments": recent_comments,
        },
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/dashboard/stats")
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/dashboard/stats")
async def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stats = _collect_stats(db)
    return templates.TemplateResponse(
        "admin/components/dashboard_stats.html",
        {"request": request, "stats": stats},
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/dashboard/site-health")
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/dashboard/site-health")
async def get_site_health(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    health = _collect_site_health(db)
    return templates.TemplateResponse(
        "admin/components/dashboard_site_health.html",
        {"request": request, "health": health},
    )


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/dashboard/quick-draft")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/dashboard/quick-draft")
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
        post_type="article",
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
    admin_path = getattr(request.state, "admin_path", settings.ADMIN_PATH.rstrip("/"))

    return JSONResponse(
        {
            "success": True,
            "id": created.id,
            "redirect_url": f"{admin_path}/posts/{created.id}/edit",
        }
    )
