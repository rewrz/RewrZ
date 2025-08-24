from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..crud import post as crud_post, comment as crud_comment, category as crud_category, tag as crud_tag
from ..core.config import settings

router = APIRouter()

# It's better to have a single templates instance, but for simplicity and to avoid circular imports,
# we create a new one here. The template path is relative to the project root.
templates = Jinja2Templates(directory="rewrz/templates")

@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/dashboard/stats")
async def get_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    """
    获取仪表盘统计数据并以HTML格式返回
    """
    if not db:
        stats = {
            "published_posts": 0,
            "draft_posts": 0,
            "total_comments": 0,
            "pending_comments": 0,
            "total_categories": 0,
            "total_tags": 0
        }
    else:
        stats = {
            "published_posts": crud_post.count_posts_by_status(db, "published"),
            "draft_posts": crud_post.count_posts_by_status(db, "draft"),
            "total_comments": crud_comment.count_comments(db),
            "pending_comments": crud_comment.count_comments_by_status(db, "pending"),
            "total_categories": crud_category.count_categories(db),
            "total_tags": crud_tag.count_tags(db)
        }
    
    return templates.TemplateResponse("admin/components/dashboard_stats.html", {"request": request, "stats": stats})