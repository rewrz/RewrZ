"""
RewrZ 博客系统主应用模块

基于FastAPI构建的个人博客系统，支持多重身份内容系统、动态主题、
反垃圾评论、版本快照等功能。采用HTMX + Tailwind CSS前端技术栈。
"""
import os
import hashlib
import secrets
import threading
from math import ceil
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError, HTTPError
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI
from contextlib import asynccontextmanager
import json
from sqlalchemy.orm import Session
from .core.template_filters import get_templates  # 导入带过滤器的模板系统
from .core.template_context import build_base_template_context, HOMEPAGE_SETTING_KEYS, DEFAULT_HOMEPAGE_SETTINGS, DEFAULT_BASE_SETTINGS
from .core.database import get_db, create_all_tables, db_manager
from .core.config import settings  # 导入settings实例
from .schemas import UserCreate, User, PostCreate, PostUpdate, SettingCreate, SettingUpdate
from .crud import user as crud_user
from .core.security import get_current_user, verify_password, decode_access_token  # 导入安全函数
from .api import auth as auth_api
from .api import installer as installer_api
from .api import posts as posts_api
from .api import media as media_api # Import the media router
from .api import comments as comments_api # Import the comments router
from .api import reactions as reactions_api # Import reactions router
from .api import settings as settings_api # Import the settings router
from .api import formats as formats_api # Import the formats router
from .api import avatars as avatars_api # 导入头像路由
from .api import snapshots as snapshots_api # 导入快照路由
from .api import seo as seo_api # 导入SEO路由
from .api import themes as themes_api # 导入主题路由
from .api import search as search_api # 导入搜索路由
from .api import rss as rss_api # 导入RSS路由
from .api import data_import_export as data_api # 导入数据导入导出路由
from .api import media_settings as media_settings_api # 导入媒体设置路由
from .api import comment_settings as comment_settings_api # 导入评论设置路由
from .api import security_center as security_center_api # 导入安全中心页面逻辑
from .api import error_config as error_config_api # 导入错误处理配置路由
from .api import admin_dashboard as admin_dashboard_api # 导入仪表盘API路由
from .api import categories as categories_api # 导入分类API路由
from .api import tags as tags_api # 导入标签API路由
from .api import captcha as captcha_api # 导入验证码API路由
from .api import anniversary_mode as anniversary_api # 导入纪念日氛围模式API路由
from .api import theme_schedule as theme_schedule_api # 导入主题调度API路由
from .api import users as users_api # 导入用户管理页面逻辑
from .core.avatar import get_avatar_service
from .core.public_profile import get_public_profile_resolver
from .crud import post as crud_post
from .crud import category as crud_category
from .crud import tag as crud_tag
from .crud import comment as crud_comment
from .crud import setting as crud_setting # Import crud_setting
from .crud import format as crud_format # 导入格式CRUD模块以修复未定义变量错误
from .models import Post, Setting
from .core import error_handler  # 导入错误处理模块
from typing import Any, Callable, Dict, List, Optional, Tuple
from sqlalchemy import select, func
from datetime import date, datetime, timedelta, timezone # 导入date和datetime用于纪念日检查和主题调度
from starlette.middleware.sessions import SessionMiddleware # 导入会话中间件
from .core.security import generate_csrf_token # 导入CSRF令牌生成函数
from .core.settings_middleware import SettingsMiddleware # 导入设置中间件
from .core.content_access import (
    has_hide_blocks,
    get_comment_unlock_cookie_name,
    render_markdown_with_hide_blocks,
)
from .core.toc import build_toc_from_html
from .core.content_utils import get_effective_content_html
from .core.content_intents import (
    choose_primary_intent_slug,
    normalize_intent_slug,
    normalize_public_intent_slug,
    to_public_post_segment,
)
from .core.media_attachments import (
    extract_image_urls,
    summarize_media_attachments,
    detect_media_flags,
    list_registered_media_attachment_keys,
    get_default_media_navigation,
)

# 全局状态，用于标记后台路由是否已注册
ADMIN_ROUTES_REGISTERED = False

# 应用生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时检查.env文件，如果不存在则重定向到安装向导
    if not os.path.exists(".env"):
        print("INFO: .env file not found. Redirecting to installer.")
        # 这不会立即重定向，但会为根路由设置条件
    create_all_tables()
    yield
    # 关闭时的清理工作（如果需要）

# 只保留一个FastAPI实例定义，包含lifespan参数，完全关闭api接口防止滥用
app = FastAPI(
    title=DEFAULT_BASE_SETTINGS["site_title"],
    description=DEFAULT_BASE_SETTINGS["tagline"],
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
    )

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="rewrz/static"), name="static")
# 挂载媒体上传目录
app.mount("/media", StaticFiles(directory=settings.MEDIA_UPLOAD_DIR), name="media")

# 配置Jinja2模板引擎（带自定义过滤器）
templates = get_templates()

_ARTICLE_FALLBACK_API_URL_DEFAULT = "https://www.loliapi.com/acg/"
_ARTICLE_FALLBACK_LOCAL_DIR_DEFAULT = "rewrz/static/images/anime/random"
_SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".svg"}
_ARTICLE_API_CACHE_DIR_NAME = "article-fallback-cache"
_ARTICLE_API_CACHE_INDEX_KEY = "article_card_api_cache_index"
_ARTICLE_API_CACHE_LAST_CLEANUP_KEY = "article_card_api_cache_last_cleanup_at"
_ARTICLE_API_CACHE_ENABLED_DEFAULT = True
_ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT = 360
_ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT = 120
_ARTICLE_API_CACHE_MAX_BYTES = 8 * 1024 * 1024
_ARTICLE_API_CACHE_HTTP_TIMEOUT_SECONDS = 8
_ARTICLE_API_CACHE_PUBLIC_PREFIX = f"/media/{_ARTICLE_API_CACHE_DIR_NAME}/"
_ARTICLE_API_CACHE_PREFETCH_INFLIGHT: set[str] = set()
_ARTICLE_API_CACHE_PREFETCH_LOCK = threading.Lock()


def _get_post_access_cookie_name(post_id: int) -> str:
    return f"post_access_{post_id}"


def _build_post_access_cookie_value(post_id: int, hashed_password: str) -> str:
    payload = f"{post_id}:{hashed_password}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_admin_authenticated(request: Request, db: Session) -> bool:
    token = request.cookies.get("access_token")
    if not token:
        return False

    payload = decode_access_token(token)
    if not payload:
        return False

    user_id = payload.get("sub")
    if user_id is None:
        return False

    try:
        return crud_user.get_user(db, user_id=int(user_id)) is not None
    except (TypeError, ValueError):
        return False


def _has_valid_password_cookie(request: Request, post_obj) -> bool:
    if not post_obj.password:
        return False

    cookie_value = request.cookies.get(_get_post_access_cookie_name(post_obj.id))
    if not cookie_value:
        return False

    expected = _build_post_access_cookie_value(post_obj.id, post_obj.password)
    return secrets.compare_digest(cookie_value, expected)


def _resolve_format_by_slug(db: Session, format_slug: str):
    normalized_slug = normalize_public_intent_slug(format_slug)
    if not normalized_slug:
        return None, None
    db_format = crud_format.get_format_by_slug(db, slug=normalized_slug)
    if db_format is not None:
        return db_format, normalized_slug
    return None, None

# 包含部分身份验证路由（保留用户信息端点，移除登录端点）
app.include_router(auth_api.router)

# 动态注册后台路由
def register_admin_routes():
    """
    根据ADMIN_PATH配置动态注册后台路由
    """
    admin_path = settings.ADMIN_PATH.rstrip('/')
    
    # 注册后台登录页面
    @app.get(f"{admin_path}/login", response_class=HTMLResponse)
    async def dynamic_admin_login_page(request: Request):
        return templates.TemplateResponse("admin/login.html", {"request": request, "admin_path": admin_path})
    
    # 注册后台登录端点（关键安全修复）
    @app.post(f"{admin_path}/auth")
    async def dynamic_admin_login(
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db),
    ):
        """
        动态后台登录端点
        这是真正的安全登录入口，路径随 ADMIN_PATH 动态变化
        """
        return await auth_api.login_for_access_token_impl(
            response,
            form_data,
            db,
            request,
            background_tasks,
        )
    
    # 注册后台仪表盘
    @app.get(f"{admin_path}/dashboard", response_class=HTMLResponse)
    async def dynamic_admin_dashboard_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await admin_dashboard_api.dashboard_page(request, db, current_user)
    
    # 注册后台设置页面
    @app.get(f"{admin_path}/settings", response_class=HTMLResponse)
    async def dynamic_admin_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await settings_api.admin_settings_page(request, db, current_user)
    
    @app.post(f"{admin_path}/settings", response_class=HTMLResponse)
    async def dynamic_update_admin_settings(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        site_title: str = Form(...),
        tagline: str = Form(...),
        noindex_site: bool = Form(DEFAULT_BASE_SETTINGS["noindex_site"]),
        block_ai_crawlers: bool = Form(DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
        site_url: str = Form(...),
        admin_email: str = Form(...),
        public_contact_email: Optional[str] = Form(None),
        site_logo_light: Optional[str] = Form(None),
        site_logo_dark: Optional[str] = Form(None),
        favicon: Optional[str] = Form(None),
        site_cover_url: Optional[str] = Form(None),
        admin_login_background_image_url: Optional[str] = Form(None),
        admin_login_background_video_url: Optional[str] = Form(None),
        copyright_info: str = Form(...),
        custom_footer_text: Optional[str] = Form(None),
        icp_beian: Optional[str] = Form(None),
        gongan_beian: Optional[str] = Form(None),
        social_links_json: str = Form("[]"),
        anniversaries_json: str = Form("[]"),
        sitemap_enabled: bool = Form(False),
        rss_enabled: bool = Form(False),
        rss_items_limit: int = Form(20),
        rss_cache_duration: int = Form(60),
        rss_description: Optional[str] = Form(None),
        homepage_posts_limit: int = Form(10),
        archive_posts_limit: int = Form(20),
        search_results_limit: int = Form(15),
        list_navigation_mode: str = Form("pagination"),
        related_posts_limit: int = Form(5), # 打赏功能相关参数之前的参数
        content_primary_mode: str = Form("markdown"),
        article_card_fallback_source: str = Form("local"),
        article_card_fallback_api_url: Optional[str] = Form(None),
        article_card_fallback_local_dir: Optional[str] = Form(None),
        article_card_api_cache_enabled: bool = Form(_ARTICLE_API_CACHE_ENABLED_DEFAULT),
        article_card_api_cache_ttl_minutes: int = Form(_ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT),
        article_card_api_cache_cleanup_minutes: int = Form(_ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT),
        # 打赏功能相关参数
        donation_enabled: bool = Form(False),
        donation_title: str = Form('如果这篇文章对您有帮助，请考虑支持作者'),
        donation_description: str = Form('您的支持是我创作的动力！'),
        donation_qr_code_url: Optional[str] = Form(None),
        donation_link_text: Optional[str] = Form(None),
        donation_link_url: Optional[str] = Form(None),
        donation_style_theme: str = Form('elegant'),
        donation_show_position: str = Form('article_end'),
        # 主页个性化设置相关参数
        homepage_mode: str = Form(DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]),
        homepage_background_image_url: Optional[str] = Form(None),
        homepage_background_video_url: Optional[str] = Form(None),
        homepage_background_music_url: Optional[str] = Form(None),
        homepage_music_autoplay: bool = Form(DEFAULT_HOMEPAGE_SETTINGS["homepage_music_autoplay"]),
        csrf_token: str = Form(...),
    ):
        return await settings_api.update_admin_settings(
            request, db, current_user, site_title, tagline, site_url, admin_email,
            public_contact_email,
            site_logo_light, site_logo_dark, favicon, site_cover_url, admin_login_background_image_url, admin_login_background_video_url, copyright_info, custom_footer_text,
            icp_beian, gongan_beian, social_links_json, anniversaries_json, sitemap_enabled,
            noindex_site, block_ai_crawlers, rss_enabled, rss_items_limit, rss_cache_duration,
            rss_description, homepage_posts_limit, archive_posts_limit, search_results_limit,
            list_navigation_mode,
            related_posts_limit,
            content_primary_mode,
            article_card_fallback_source, article_card_fallback_api_url, article_card_fallback_local_dir,
            article_card_api_cache_enabled, article_card_api_cache_ttl_minutes, article_card_api_cache_cleanup_minutes,
            # 打赏功能相关参数
            donation_enabled, donation_title, donation_description,
            donation_qr_code_url, donation_link_text, donation_link_url,
            donation_style_theme, donation_show_position,
            # 主页个性化设置
            homepage_mode, homepage_background_image_url, homepage_background_video_url,
            homepage_background_music_url, homepage_music_autoplay,
            csrf_token
        )

    # 注册后台用户管理页面（当前登录用户资料）
    @app.get(f"{admin_path}/users", response_class=HTMLResponse)
    async def dynamic_admin_users_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await users_api.admin_users_page(request, db, current_user)

    @app.post(f"{admin_path}/users", response_class=HTMLResponse)
    async def dynamic_update_admin_user_profile(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
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
    ):
        return await users_api.update_admin_user_profile(
            request=request,
            db=db,
            current_user=current_user,
            username=username,
            email=email,
            display_name=display_name,
            bio=bio,
            website=website,
            use_gravatar=use_gravatar,
            creator_profile_cover_url=creator_profile_cover_url,
            creator_profile_micro_cover_url=creator_profile_micro_cover_url,
            creator_profile_poem_cover_url=creator_profile_poem_cover_url,
            creator_profile_headline=creator_profile_headline,
            creator_profile_article_bio=creator_profile_article_bio,
            creator_profile_micro_bio=creator_profile_micro_bio,
            creator_profile_poem_bio=creator_profile_poem_bio,
            creator_profile_location=creator_profile_location,
            creator_profile_motto=creator_profile_motto,
            csrf_token=csrf_token,
        )
    
    # 注册后台路径更新API端点
    @app.post(f"{admin_path}/api/v1/update-admin-path")
    @app.post(f"{admin_path}/api/update-admin-path")
    async def dynamic_update_admin_path(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await settings_api.update_admin_path(request, db, current_user)
    
    # 注册后台媒体页面
    @app.get(f"{admin_path}/media", response_class=HTMLResponse) 
    async def dynamic_admin_media_page(request: Request, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
        return await media_api.media_library_page(request, db, current_user)
    
    # 注册后台媒体设置页面
    @app.get(f"{admin_path}/media/settings", response_class=HTMLResponse)
    async def dynamic_admin_media_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await media_settings_api.media_settings_page(request, db, current_user)
    
    # 注册后台主题页面
    @app.get(f"{admin_path}/themes", response_class=HTMLResponse)
    async def dynamic_admin_themes_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await themes_api.admin_themes_page(request, db, current_user)
    
    @app.post(f"{admin_path}/themes/update")
    async def dynamic_update_theme(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        form_data = await request.form()
        return await themes_api.update_theme_settings(
            request=request,
            db=db,
            current_user=current_user,
            current_theme=form_data.get("current_theme", "light"),
            current_atmosphere=form_data.get("current_atmosphere"),
            auto_theme_enabled=bool(form_data.get("auto_theme_enabled")),
            csrf_token=form_data.get("csrf_token", "")
        )
    
    @app.post(f"{admin_path}/themes/custom")
    async def dynamic_create_custom_theme(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        form_data = await request.form()
        return await themes_api.create_custom_theme(
            request=request,
            db=db,
            current_user=current_user,
            theme_name=form_data.get("theme_name", ""),
            theme_data=form_data.get("theme_data", ""),
            csrf_token=form_data.get("csrf_token", "")
        )
    
    @app.delete(f"{admin_path}/themes/custom/{{theme_name}}")
    async def dynamic_delete_custom_theme(theme_name: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await themes_api.delete_custom_theme(theme_name, request, db, current_user)
    
    @app.post(f"{admin_path}/themes/schedule")
    async def dynamic_schedule_themes(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        form_data = await request.form()
        return await themes_api.schedule_themes(
            request=request,
            db=db,
            current_user=current_user,
            schedule_data=form_data.get("schedule_data", ""),
            csrf_token=form_data.get("csrf_token", "")
        )
    
    # 注册后台文章页面
    @app.get(f"{admin_path}/posts/new", response_class=HTMLResponse)
    async def dynamic_admin_new_post_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await posts_api.new_post_page(request, db, current_user)
    
    # 注册后台文章列表管理页面
    @app.get(f"{admin_path}/posts", response_class=HTMLResponse)
    async def dynamic_admin_posts_list_page(
        request: Request, 
        search: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db), 
        current_user: User = Depends(get_current_user)
    ):
        from math import ceil
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import joinedload
        from .models import Post, Comment
        from .crud import post as crud_post

        search = (search or "").strip() or None
        status = (status or "").strip() or None
        category = (category or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [10, 20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        base_conditions = [Post.post_type.in_(["post", "article"])]
        filter_conditions = list(base_conditions)

        if status:
            filter_conditions.append(Post.status == status)

        category_id: Optional[int] = None
        if category:
            try:
                category_id = int(category)
            except ValueError:
                category_id = None
            if category_id is not None:
                filter_conditions.append(Post.categories.any(id=category_id))

        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Post.title.ilike(like),
                    Post.excerpt.ilike(like),
                    Post.content_markdown.ilike(like),
                    Post.content_html.ilike(like),
                )
            )

        total_articles = db.execute(
            select(func.count(Post.id)).where(*base_conditions)
        ).scalar_one()
        filtered_total = db.execute(
            select(func.count(Post.id)).where(*filter_conditions)
        ).scalar_one()

        total_pages = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * resolved_page_size
        posts = db.execute(
            select(Post)
            .options(joinedload(Post.categories), joinedload(Post.tags), joinedload(Post.formats))
            .where(*filter_conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(resolved_page_size)
        ).unique().scalars().all()

        # 附加阅读量
        try:
            crud_post._attach_views_metrics(db, posts)
        except Exception:
            for post in posts:
                setattr(post, "views", 0)
                setattr(post, "views_count", 0)

        # 评论数量（包含全部状态）
        comment_count_map = {}
        post_ids = [post.id for post in posts]
        if post_ids:
            comment_rows = db.execute(
                select(Comment.post_id, func.count(Comment.id))
                .where(Comment.post_id.in_(post_ids))
                .group_by(Comment.post_id)
            ).all()
            comment_count_map = {post_id: count for post_id, count in comment_rows}
        for post in posts:
            setattr(post, "comment_count", int(comment_count_map.get(post.id, 0)))

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if status:
                params["status"] = status
            if category_id is not None:
                params["category"] = str(category_id)
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_pages, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_pages,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_pages else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        categories = crud_category.get_categories(db)
        
        return templates.TemplateResponse("admin/posts_list.html", {
            "request": request, 
            "posts": posts, 
            "categories": categories,
            "search_query": search or "",
            "selected_status": status or "",
            "selected_category": str(category_id) if category_id is not None else "",
            "pagination": pagination,
            "total_articles": total_articles,
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册获取分类选项的API端点
    @app.get(f"{admin_path}/api/v1/categories/options")
    @app.get(f"{admin_path}/api/categories/options")
    async def dynamic_get_category_options(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        categories = crud_category.get_categories(db)
        options_html = '<option value="">全部分类</option>'
        for category in categories:
            options_html += f'<option value="{category.id}">{category.name}</option>'
        return HTMLResponse(content=options_html)
    
    @app.post(f"{admin_path}/posts/new")
    async def dynamic_create_post(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        content_html: Optional[str] = Form(None),
        editor_mode: Optional[str] = Form(None),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        visibility: str = Form("public"),
        password: Optional[str] = Form(None),
        allow_comments: bool = Form(True),
        category_ids: Optional[List[int]] = Form(None),
        tags: Optional[str] = Form(None),
        format_id: Optional[int] = Form(None),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.create_post_api(
            request=request,
            title=title,
            content=content,
            content_html=content_html,
            editor_mode=editor_mode,
            slug=slug,
            excerpt=excerpt,
            featured_image_url=featured_image_url,
            status=status,
            visibility=visibility,
            password=password,
            allow_comments=allow_comments,
            category_ids=category_ids,
            tags=tags,
            format_id=format_id,
            license_type=license_type,
            csrf_token=csrf_token,
            db=db,
            current_user=current_user,
        )
    
    @app.post(f"{admin_path}/posts/{{post_id}}")
    async def dynamic_update_post(
        post_id: int,
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        content_html: Optional[str] = Form(None),
        editor_mode: Optional[str] = Form(None),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        visibility: str = Form("public"),
        password: Optional[str] = Form(None),
        allow_comments: bool = Form(True),
        category_ids: Optional[List[int]] = Form(None),
        tags: Optional[str] = Form(None),
        format_id: Optional[int] = Form(None),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.update_post_api(
            request=request,
            post_id=post_id,
            title=title,
            content=content,
            content_html=content_html,
            editor_mode=editor_mode,
            slug=slug,
            excerpt=excerpt,
            featured_image_url=featured_image_url,
            status=status,
            visibility=visibility,
            password=password,
            allow_comments=allow_comments,
            category_ids=category_ids,
            tags=tags,
            format_id=format_id,
            license_type=license_type,
            csrf_token=csrf_token,
            db=db,
            current_user=current_user,
        )
    
    # 注册后台分类管理页面
    @app.get(f"{admin_path}/categories", response_class=HTMLResponse)
    async def dynamic_admin_categories_page(
        request: Request,
        search: Optional[str] = None,
        usage: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from math import ceil
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import selectinload
        from .models import Category
        from .models.post import post_categories

        search = (search or "").strip() or None
        usage = (usage or "").strip().lower() or None
        if usage not in {"used", "unused"}:
            usage = None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Category.name.ilike(like),
                    Category.slug.ilike(like),
                    Category.description.ilike(like),
                )
            )
        if usage == "used":
            filter_conditions.append(Category.posts.any())
        elif usage == "unused":
            filter_conditions.append(~Category.posts.any())

        total_categories = db.execute(select(func.count(Category.id))).scalar_one()
        used_categories = db.execute(
            select(func.count(Category.id)).where(Category.posts.any())
        ).scalar_one()
        unused_categories = max(0, total_categories - used_categories)
        total_post_bindings = db.execute(
            select(func.count()).select_from(post_categories)
        ).scalar_one()

        filtered_total_query = select(func.count(Category.id))
        if filter_conditions:
            filtered_total_query = filtered_total_query.where(*filter_conditions)
        filtered_total = db.execute(filtered_total_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        categories_query = select(Category).options(selectinload(Category.posts))
        if filter_conditions:
            categories_query = categories_query.where(*filter_conditions)
        categories = db.execute(
            categories_query
            .order_by(Category.name.asc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        for category in categories:
            setattr(category, "post_count", len(category.posts) if category.posts else 0)

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if usage:
                params["usage"] = usage
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/categories_list.html", {
            "request": request,
            "categories": categories,
            "search_query": search or "",
            "selected_usage": usage or "",
            "pagination": pagination,
            "stats": {
                "total": total_categories,
                "used": used_categories,
                "unused": unused_categories,
                "post_bindings": total_post_bindings,
            },
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册后台标签管理页面
    @app.get(f"{admin_path}/tags", response_class=HTMLResponse)
    async def dynamic_admin_tags_page(
        request: Request,
        search: Optional[str] = None,
        usage: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from math import ceil
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import selectinload
        from .models import Tag
        from .models.post import post_tags

        search = (search or "").strip() or None
        usage = (usage or "").strip().lower() or None
        if usage not in {"used", "unused"}:
            usage = None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Tag.name.ilike(like),
                    Tag.slug.ilike(like),
                )
            )
        if usage == "used":
            filter_conditions.append(Tag.posts.any())
        elif usage == "unused":
            filter_conditions.append(~Tag.posts.any())

        total_tags = db.execute(select(func.count(Tag.id))).scalar_one()
        used_tags = db.execute(
            select(func.count(Tag.id)).where(Tag.posts.any())
        ).scalar_one()
        unused_tags = max(0, total_tags - used_tags)
        total_post_bindings = db.execute(
            select(func.count()).select_from(post_tags)
        ).scalar_one()

        filtered_total_query = select(func.count(Tag.id))
        if filter_conditions:
            filtered_total_query = filtered_total_query.where(*filter_conditions)
        filtered_total = db.execute(filtered_total_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        tags_query = select(Tag).options(selectinload(Tag.posts))
        if filter_conditions:
            tags_query = tags_query.where(*filter_conditions)
        tags = db.execute(
            tags_query
            .order_by(Tag.name.asc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        for tag in tags:
            setattr(tag, "post_count", len(tag.posts) if tag.posts else 0)

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if usage:
                params["usage"] = usage
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/tags_list.html", {
            "request": request,
            "tags": tags,
            "search_query": search or "",
            "selected_usage": usage or "",
            "pagination": pagination,
            "stats": {
                "total": total_tags,
                "used": used_tags,
                "unused": unused_tags,
                "post_bindings": total_post_bindings,
            },
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册后台评论管理页面
    @app.get(f"{admin_path}/comments", response_class=HTMLResponse)
    async def dynamic_admin_comments_page(
        request: Request, 
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db), 
        current_user: User = Depends(get_current_user)
    ):
        from math import ceil
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import joinedload
        from .models import Comment, Post

        status = (status or "").strip() or None
        search = (search or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if status:
            filter_conditions.append(Comment.status == status)
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Comment.author_name.ilike(like),
                    Comment.author_email.ilike(like),
                    Comment.content.ilike(like),
                    Post.title.ilike(like),
                    Comment.ip_address.ilike(like),
                    Comment.user_agent.ilike(like),
                )
            )

        total_comments = db.execute(select(func.count(Comment.id))).scalar_one()
        pending_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "pending")
        ).scalar_one()
        approved_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "approved")
        ).scalar_one()
        spam_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "spam")
        ).scalar_one()

        count_query = select(func.count(Comment.id)).outerjoin(Post, Post.id == Comment.post_id)
        if filter_conditions:
            count_query = count_query.where(*filter_conditions)
        filtered_total = db.execute(count_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        comments_query = (
            select(Comment)
            .outerjoin(Post, Post.id == Comment.post_id)
            .options(
                joinedload(Comment.post),
                joinedload(Comment.parent),
            )
        )
        if filter_conditions:
            comments_query = comments_query.where(*filter_conditions)
        comments = db.execute(
            comments_query.order_by(Comment.created_at.desc()).offset(offset).limit(resolved_page_size)
        ).scalars().all()

        avatar_service = get_avatar_service(db)
        comments_with_avatars = []
        for comment in comments:
            avatar_url = avatar_service.get_comment_avatar_url(
                author_email=comment.author_email,
                author_id=None,
                size=40
            )
            comments_with_avatars.append({
                "comment": comment,
                "avatar_url": avatar_url
            })

        def _build_page_url(target_page: int) -> str:
            params = {}
            if status:
                params["status"] = status
            if search:
                params["search"] = search
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/comments_list.html", {
            "request": request, 
            "comments_with_avatars": comments_with_avatars, 
            "user": current_user,
            "admin_path": admin_path,
            "current_status": status,
            "search_query": search or "",
            "pagination": pagination,
            "total_comments": total_comments,
            "status_counts": {
                "pending": pending_count,
                "approved": approved_count,
                "spam": spam_count,
            },
        })
    
    # 注册后台页面管理页面
    @app.get(f"{admin_path}/pages", response_class=HTMLResponse)
    async def dynamic_admin_pages_page(
        request: Request,
        search: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from math import ceil
        from sqlalchemy import select, func, or_
        from .models import Post, Comment
        from .crud import post as crud_post

        search = (search or "").strip() or None
        status = (status or "").strip() or None
        visibility = (visibility or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [10, 20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        base_conditions = [Post.post_type == "page"]
        filter_conditions = list(base_conditions)
        if status:
            filter_conditions.append(Post.status == status)
        if visibility:
            filter_conditions.append(Post.visibility == visibility)
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Post.title.ilike(like),
                    Post.excerpt.ilike(like),
                    Post.content_markdown.ilike(like),
                    Post.content_html.ilike(like),
                    Post.slug.ilike(like),
                )
            )

        total_pages_count = db.execute(
            select(func.count(Post.id)).where(*base_conditions)
        ).scalar_one()
        filtered_total = db.execute(
            select(func.count(Post.id)).where(*filter_conditions)
        ).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count

        offset = (page - 1) * resolved_page_size
        pages = db.execute(
            select(Post)
            .where(*filter_conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        # 附加阅读量
        try:
            crud_post._attach_views_metrics(db, pages)
        except Exception:
            for item in pages:
                setattr(item, "views", 0)
                setattr(item, "views_count", 0)

        # 评论数量（全部状态）
        page_ids = [item.id for item in pages]
        comment_count_map = {}
        if page_ids:
            comment_rows = db.execute(
                select(Comment.post_id, func.count(Comment.id))
                .where(Comment.post_id.in_(page_ids))
                .group_by(Comment.post_id)
            ).all()
            comment_count_map = {post_id: count for post_id, count in comment_rows}
        for item in pages:
            setattr(item, "comment_count", int(comment_count_map.get(item.id, 0)))

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if status:
                params["status"] = status
            if visibility:
                params["visibility"] = visibility
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/pages_list.html", {
            "request": request, 
            "pages": pages,
            "search_query": search or "",
            "selected_status": status or "",
            "selected_visibility": visibility or "",
            "pagination": pagination,
            "total_pages_count": total_pages_count,
            "user": current_user,
            "admin_path": admin_path
        })
    
    @app.post(f"{admin_path}/pages/new")
    async def dynamic_create_page(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        content_html: Optional[str] = Form(None),
        editor_mode: Optional[str] = Form(None),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        visibility: str = Form("public"),
        password: Optional[str] = Form(None),
        allow_comments: bool = Form(True),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.create_page_api(
            request=request,
            title=title,
            content=content,
            content_html=content_html,
            editor_mode=editor_mode,
            slug=slug,
            excerpt=excerpt,
            featured_image_url=featured_image_url,
            status=status,
            visibility=visibility,
            password=password,
            allow_comments=allow_comments,
            license_type=license_type,
            csrf_token=csrf_token,
            db=db,
            current_user=current_user,
        )
    
    @app.post(f"{admin_path}/pages/{{page_id}}")
    async def dynamic_update_page(
        page_id: int,
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        content_html: Optional[str] = Form(None),
        editor_mode: Optional[str] = Form(None),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        visibility: str = Form("public"),
        password: Optional[str] = Form(None),
        allow_comments: bool = Form(True),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.update_page_api(
            request=request,
            page_id=page_id,
            title=title,
            content=content,
            content_html=content_html,
            editor_mode=editor_mode,
            slug=slug,
            excerpt=excerpt,
            featured_image_url=featured_image_url,
            status=status,
            visibility=visibility,
            password=password,
            allow_comments=allow_comments,
            license_type=license_type,
            csrf_token=csrf_token,
            db=db,
            current_user=current_user,
        )
    
    # 注册后台系统信息页面
    @app.get(f"{admin_path}/system-info", response_class=HTMLResponse)
    async def dynamic_admin_system_info_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .api import system_info as system_info_api
        return await system_info_api.system_info_page(request, db, current_user)
    
    @app.get(f"{admin_path}/api/v1/system-info")
    @app.get(f"{admin_path}/api/system-info")
    @app.get(f"{admin_path}/api/system/info")
    async def dynamic_get_system_info_api(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .api import system_info as system_info_api
        return await system_info_api.get_system_info_api(db, current_user)

    # 注册错误处理配置页面
    @app.get(f"{admin_path}/error-settings", response_class=HTMLResponse)
    async def dynamic_admin_error_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await error_config_api.error_settings_page(request, db, current_user)
    
    # 注册评论设置页面
    @app.get(f"{admin_path}/comment-settings", response_class=HTMLResponse)
    async def dynamic_admin_comment_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await comment_settings_api.comment_settings_page(request, db, current_user)

    # 注册安全中心页面
    @app.get(f"{admin_path}/security-center", response_class=HTMLResponse)
    async def dynamic_admin_security_center_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await security_center_api.security_center_page(request, db, current_user)

    @app.post(f"{admin_path}/security-center", response_class=HTMLResponse)
    async def dynamic_update_security_center(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        login_max_attempts: int = Form(3),
        login_ban_minutes: int = Form(15),
        new_ip_login_alert_enabled: bool = Form(False),
        comment_rate_limit_per_min: int = Form(30),
        csrf_token: str = Form(...),
    ):
        return await security_center_api.update_security_center(
            request=request,
            db=db,
            current_user=current_user,
            login_max_attempts=login_max_attempts,
            login_ban_minutes=login_ban_minutes,
            new_ip_login_alert_enabled=new_ip_login_alert_enabled,
            comment_rate_limit_per_min=comment_rate_limit_per_min,
            csrf_token=csrf_token,
        )

    # 注册数据管理页面
    @app.get(f"{admin_path}/data-management", response_class=HTMLResponse)
    async def dynamic_admin_data_management_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await data_api.data_management_page(request, db, current_user)

    # 包含数据导入导出路由
    app.include_router(data_api.router, prefix=admin_path)
    
    # 注册数据统计API
    @app.get(f"{admin_path}/api/v1/dashboard/stats")
    @app.get(f"{admin_path}/api/dashboard/stats")
    async def dynamic_get_dashboard_stats(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from .api import admin_dashboard as admin_dashboard_api
        return await admin_dashboard_api.get_dashboard_stats(request, db, current_user)

    @app.get(f"{admin_path}/api/v1/dashboard/site-health")
    @app.get(f"{admin_path}/api/dashboard/site-health")
    async def dynamic_get_dashboard_site_health(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from .api import admin_dashboard as admin_dashboard_api
        return await admin_dashboard_api.get_site_health(request, db, current_user)

    @app.post(f"{admin_path}/api/v1/dashboard/quick-draft")
    @app.post(f"{admin_path}/api/dashboard/quick-draft")
    async def dynamic_quick_draft(
        request: Request,
        title: str = Form(""),
        content: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        from .api import admin_dashboard as admin_dashboard_api
        return await admin_dashboard_api.create_quick_draft(
            request=request,
            title=title,
            content=content,
            csrf_token=csrf_token,
            db=db,
            current_user=current_user,
        )

    """
    动态注册错误处理配置页面
    """
    @app.post(f"{admin_path}/error-settings")
    async def dynamic_update_error_settings(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        enable_custom_error_pages: bool = Form(False),
        error_page_template: str = Form("default"),
        custom_error_404_title: str = Form("页面未找到"),
        custom_error_404_message: str = Form("抱歉，您访问的页面不存在。"),
        custom_error_500_title: str = Form("服务器内部错误"),
        custom_error_500_message: str = Form("抱歉，服务器遇到了一些问题，请稍后再试。"),
        custom_error_403_title: str = Form("访问被禁止"),
        custom_error_403_message: str = Form("抱歉，您没有权限访问此页面。"),
        custom_error_400_title: str = Form("请求错误"),
        custom_error_400_message: str = Form("抱歉，您的请求存在问题，请检查后重试。"),
        enable_error_caching: bool = Form(False),
        error_cache_duration: int = Form(3600),
        enable_error_logging: bool = Form(False),
        log_level: str = Form("INFO"),
        enable_performance_optimization: bool = Form(False),
        related_posts_cache_strategy: str = Form("aggressive"),
        reading_time_cache_duration: int = Form(7200),
        csrf_token: str = Form(...)
    ):
        return await error_config_api.update_error_settings(
            request, db, current_user,
            enable_custom_error_pages, error_page_template,
            custom_error_404_title, custom_error_404_message,
            custom_error_500_title, custom_error_500_message,
            custom_error_403_title, custom_error_403_message,
            custom_error_400_title, custom_error_400_message,
            enable_error_caching, error_cache_duration,
            enable_error_logging, log_level,
            enable_performance_optimization, related_posts_cache_strategy,
            reading_time_cache_duration, csrf_token
        )
    
    # 动态注册分类API路由（v1 + 兼容旧路径）
    app.include_router(categories_api.router, prefix=admin_path)
    app.include_router(categories_api.legacy_router, prefix=admin_path)
    
    # 动态注册标签API路由（v1 + 兼容旧路径）
    app.include_router(tags_api.router, prefix=admin_path)
    app.include_router(tags_api.legacy_router, prefix=admin_path)

    @app.get("/{format_slug}/{post_slug}", response_class=HTMLResponse)
    async def read_post(request: Request, format_slug: str, post_slug: str, db: Session = Depends(get_db)):
        """
        文章详情页路由
        
        根据文章别名显示单篇文章的详细内容，包含动态SEO元数据
        """
        db_post = crud_post.get_post_by_slug(db, slug=post_slug)
        is_admin = _is_admin_authenticated(request, db)

        if db_post is None or db_post.post_type == "page" or (db_post.status != "published" and not is_admin):
            raise HTTPException(status_code=404, detail="Post not found")

        # 私密内容仅管理员可访问
        if db_post.visibility == "private" and not is_admin:
            raise HTTPException(status_code=404, detail="Post not found")

        # 密码保护内容：未通过验证时展示密码输入页
        if db_post.visibility == "password" and not is_admin and not _has_valid_password_cookie(request, db_post):
            context = build_base_template_context(request)
            context.update({
                "post": db_post,
                "next_url": request.url.path,
                "error_message": None,
            })
            return templates.TemplateResponse("password_protected.html", context, status_code=401)
        
        # 验证路由段与文章主类型是否匹配（只使用内容类型，不再按媒体类型分流）
        raw_format_slugs = [fmt.slug for fmt in db_post.formats if getattr(fmt, "slug", None)] if db_post.formats else []
        normalized_intents = {
            intent_slug
            for intent_slug in (normalize_intent_slug(slug) for slug in raw_format_slugs)
            if intent_slug is not None
        }
        if not normalized_intents:
            normalized_intents = {"article"}

        requested_intent = normalize_public_intent_slug(format_slug)
        if requested_intent not in normalized_intents:
            preferred_intent = choose_primary_intent_slug(normalized_intents)
            preferred_segment = to_public_post_segment(preferred_intent)
            return RedirectResponse(url=f"/{preferred_segment}/{post_slug}", status_code=301)

        active_format_slug = requested_intent or "article"

        # 访问即计数：文章详情页浏览量 +1
        try:
            latest_views = _increment_post_views_metric(db, db_post.id)
            setattr(db_post, "views_count", latest_views)
            setattr(db_post, "views", latest_views)
        except Exception:
            db.rollback()
        
        # 获取SEO元数据
        from .api.seo import _generate_post_seo_data
        seo_data = _generate_post_seo_data(db_post, request, db)
        
        # 获取打赏配置
        from .core.donation_system import get_donation_system
        donation_system = get_donation_system(db)
        donation_config = donation_system.settings

        # 处理评论后可见内容
        can_view_hidden = is_admin or request.cookies.get(get_comment_unlock_cookie_name(db_post.id)) == "true"
        display_content_html = get_effective_content_html(db_post.content_markdown, db_post.content_html)
        if db_post.content_markdown and has_hide_blocks(db_post.content_markdown):
            display_content_html = render_markdown_with_hide_blocks(
                db_post.content_markdown,
                db_post.id,
                can_view_hidden=can_view_hidden,
            )

        # 自动目录（TOC）：达到阈值时生成
        display_content_html, toc_items = build_toc_from_html(display_content_html, min_headings=3)
        profile_resolver = get_public_profile_resolver()
        format_profile = profile_resolver.resolve_format_profile(request, db, active_format_slug)
        _attach_post_author_profiles(db, [db_post], fallback_name=format_profile.get("display_name", "博主"))

        # 构建模板上下文（现在包含统一的设置数据）
        context = build_base_template_context(request)
        context.update({
            "post": db_post,
            "seo_data": seo_data,
            "donation_config": donation_config,
            "display_content_html": display_content_html,
            "toc_items": toc_items,
            "active_format_slug": active_format_slug,
            "format_profile": format_profile,
        })
        
        return templates.TemplateResponse("post_detail.html", context)

    # 动态页面路由处理器
    @app.get("/{page_slug}", response_class=HTMLResponse)
    async def read_page(request: Request, page_slug: str, db: Session = Depends(get_db)):
        """
        页面详情页路由
        
        根据页面别名显示单个页面的详细内容
        """
        # 首先检查是否是特殊路由（避免与现有路由冲突）
        if page_slug in ["installer", "static", "api", "favicon.ico"]:
            raise HTTPException(status_code=404, detail="Page not found")
        
        is_admin = _is_admin_authenticated(request, db)

        # 检查是否存在具有该别名的页面
        db_page = crud_post.get_post_by_slug(db, slug=page_slug)
        if db_page is None or db_page.post_type != "page" or (db_page.status != "published" and not is_admin):
            # 如果没有找到页面，检查是否是其他特殊路由
            raise HTTPException(status_code=404, detail="Page not found")

        # 私密页面仅管理员可访问
        if db_page.visibility == "private" and not is_admin:
            raise HTTPException(status_code=404, detail="Page not found")

        # 密码保护页面：未验证则返回密码输入页
        if db_page.visibility == "password" and not is_admin and not _has_valid_password_cookie(request, db_page):
            context = build_base_template_context(request)
            context.update({
                "post": db_page,
                "next_url": request.url.path,
                "error_message": None,
            })
            return templates.TemplateResponse("password_protected.html", context, status_code=401)

        # 访问即计数：页面详情浏览量 +1
        try:
            latest_views = _increment_post_views_metric(db, db_page.id)
            setattr(db_page, "views_count", latest_views)
            setattr(db_page, "views", latest_views)
        except Exception:
            db.rollback()
        
        # 获取SEO元数据
        from .api.seo import _generate_post_seo_data
        seo_data = _generate_post_seo_data(db_page, request, db)

        # 处理评论后可见内容
        can_view_hidden = is_admin or request.cookies.get(get_comment_unlock_cookie_name(db_page.id)) == "true"
        display_content_html = get_effective_content_html(db_page.content_markdown, db_page.content_html)
        if db_page.content_markdown and has_hide_blocks(db_page.content_markdown):
            display_content_html = render_markdown_with_hide_blocks(
                db_page.content_markdown,
                db_page.id,
                can_view_hidden=can_view_hidden,
            )

        display_content_html, toc_items = build_toc_from_html(display_content_html, min_headings=3)
        
        # 构建模板上下文（现在包含统一的设置数据）
        context = build_base_template_context(request)
        context.update({
            "post": db_page,
            "seo_data": seo_data,
            "display_content_html": display_content_html,
            "toc_items": toc_items,
        })
        
        return templates.TemplateResponse("page.html", context)

# 包含安装向导路由
app.include_router(installer_api.router)
# 包含文章路由
app.include_router(posts_api.router)
# 包含媒体路由
app.include_router(media_api.router)
# 包含评论路由
app.include_router(comments_api.router)
# 包含互动表态路由
app.include_router(reactions_api.router)
# 包含设置路由
app.include_router(settings_api.router)
# 包含格式路由
app.include_router(formats_api.router)
# 包含头像路由
app.include_router(avatars_api.router)
# 包含快照路由
app.include_router(snapshots_api.router)
# 包含SEO路由
app.include_router(seo_api.router)
# 包含主题路由
app.include_router(themes_api.router)
# 包含搜索路由
app.include_router(search_api.router)
# 包含RSS路由
app.include_router(rss_api.router)
# 包含媒体设置路由
app.include_router(media_settings_api.router)
# 包含评论设置路由
app.include_router(comment_settings_api.router)
# 包含错误处理配置路由
app.include_router(error_config_api.router)
# 包含仪表盘API路由
app.include_router(admin_dashboard_api.router)
# 包含验证码API路由
app.include_router(captcha_api.router)
app.include_router(anniversary_api.router, prefix="/api/v1")
app.include_router(anniversary_api.router, prefix="/api")
# 包含主题调度API路由  
app.include_router(theme_schedule_api.router, prefix="/api/v1")
app.include_router(theme_schedule_api.router, prefix="/api")

# 抽取：构建全局请求上下文（初始化默认值、读取设置、主题调度/纪念日、后台路径）
def _populate_global_request_state(request: Request) -> None:
    # 初始化全局上下文变量
    request.state.atmosphere_class = ""
    request.state.site_title = DEFAULT_BASE_SETTINGS["site_title"]
    request.state.tagline = DEFAULT_BASE_SETTINGS["tagline"]
    request.state.noindex_site = DEFAULT_BASE_SETTINGS["noindex_site"]
    request.state.block_ai_crawlers = DEFAULT_BASE_SETTINGS["block_ai_crawlers"]
    request.state.admin_path = get_admin_path()  # 添加后台路径
    request.state.csrf_token = ""  # 初始化CSRF令牌
    # 初始化主页个性化设置（集中默认值）
    for k, v in DEFAULT_HOMEPAGE_SETTINGS.items():
        setattr(request.state, k, v)

    db = getattr(request.state, "db", None)
    db_gen = None
    if db is None:
        db_gen = get_db()
        db = next(db_gen)
    if db is None:
        return
    try:
        # 获取并设置所有全局上下文
        settings_keys = dict(DEFAULT_BASE_SETTINGS)
        # 主页个性化设置
        settings_keys.update(DEFAULT_HOMEPAGE_SETTINGS)
        all_settings = crud_setting.get_settings_by_keys(db, list(settings_keys.keys()))
        for key, default_value in settings_keys.items():
            setattr(request.state, key, all_settings.get(key, default_value))

        # 氛围模式优先级：纪念日氛围 > 前端明暗模式 > 主题管理调度
        
        # 1. 最高优先级：检查纪念日氛围模式
        # 优先检查 anniversaries_json（常规设置），然后检查 anniversaries（旧版本兼容）
        anniversaries_setting = crud_setting.get_setting(db, key="anniversaries_json")
        if not anniversaries_setting:
            anniversaries_setting = crud_setting.get_setting(db, key="anniversaries")
        
        anniversary_atmosphere = None
        if anniversaries_setting and anniversaries_setting.value:
            try:
                anniversaries_raw = anniversaries_setting.value
                if isinstance(anniversaries_raw, dict):
                    anniversaries_raw = anniversaries_raw.get("value", anniversaries_raw)
                if isinstance(anniversaries_raw, str):
                    anniversaries = json.loads(anniversaries_raw)
                elif isinstance(anniversaries_raw, list):
                    anniversaries = anniversaries_raw
                else:
                    anniversaries = []
                
                today = date.today()
                for anniversary in anniversaries:
                    if isinstance(anniversary, dict) and "month" in anniversary and "day" in anniversary and "type" in anniversary:
                        try:
                            if anniversary["month"] == today.month and anniversary["day"] == today.day:
                                anniversary_atmosphere = themes_api.normalize_atmosphere_name(anniversary['type'])
                                break
                        except (KeyError, TypeError):
                            continue
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                # 如果解析失败，忽略纪念日设置
                pass
        
        # 如果有纪念日氛围，直接应用（最高优先级）
        if anniversary_atmosphere:
            request.state.atmosphere_class = f"atmosphere-{anniversary_atmosphere}"
        else:
            # 2. 中等优先级：前端用户明暗模式切换（由前端JavaScript处理）
            # 这里不设置atmosphere_class，让前端JavaScript根据用户偏好处理
            
            # 3. 最低优先级：检查主题管理中的调度设置
            scheduled_atmosphere = None
            schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
            if schedule_setting and schedule_setting.value:
                schedule = schedule_setting.value.get("value", [])
                today = date.today()
                
                for item in schedule:
                    if isinstance(item, dict) and "start_date" in item and "end_date" in item:
                        try:
                            start_date = datetime.strptime(item["start_date"], "%Y-%m-%d").date()
                            end_date = datetime.strptime(item["end_date"], "%Y-%m-%d").date()
                            
                            if start_date <= today <= end_date:
                                scheduled_atmosphere = themes_api.normalize_atmosphere_name(item.get("atmosphere"))
                                break
                        except (ValueError, KeyError):
                            continue
            
            # 仅在没有纪念日氛围时应用调度氛围
            if scheduled_atmosphere:
                request.state.atmosphere_class = f"atmosphere-{scheduled_atmosphere}"
    finally:
        try:
            if db_gen is not None:
                db_gen.close()  # 关闭 get_db() 生成器，确保会话释放到连接池
        except Exception:
            pass

# 抽取：确保 CSRF 令牌存在（优先使用会话，否则生成临时令牌）
def _ensure_csrf_token(request: Request) -> None:
    try:
        if hasattr(request, 'session'):
            csrf_token = request.session.get("csrf_token")
            if not csrf_token:
                csrf_token = generate_csrf_token()
                request.session["csrf_token"] = csrf_token
            request.state.csrf_token = csrf_token
        else:
            # 如果没有会话（例如API测试），则生成一个临时令牌
            request.state.csrf_token = generate_csrf_token()
    except Exception as e:
        # 记录实际的异常，而不是静默忽略
        print(f"ERROR: Failed to handle CSRF token: {e}")
        # 异常情况下，也生成一个临时令牌以避免应用崩溃
        request.state.csrf_token = generate_csrf_token()

@app.middleware("http")
async def add_global_context(request: Request, call_next):
    global ADMIN_ROUTES_REGISTERED
    # 动态注册后台路由（如果需要）
    # 在安装完成后，通过首次请求动态加载后台路由，避免重启服务器
    if settings.installation_complete and not ADMIN_ROUTES_REGISTERED:
        register_admin_routes()
        ADMIN_ROUTES_REGISTERED = True

    # 安装完成后，不再暴露 installer 路径，避免通过重定向等方式泄露后台入口信息
    if settings.installation_complete and request.url.path.startswith("/installer"):
        return RedirectResponse(url="/")

    # 检查.env文件并重定向到安装向导
    if not settings.installation_complete and \
       not request.url.path.startswith("/installer") and \
       not request.url.path.startswith("/static") and \
       not request.url.path.startswith("/api"):
        return RedirectResponse(url="/installer")

    # 复用一个 request 级数据库会话给模板层（如响应式图片、相关文章过滤器）
    request_db_gen = None
    try:
        request_db_gen = get_db()
        request.state.db = next(request_db_gen)
    except Exception:
        request.state.db = None

    try:
        # 构建全局上下文并确保 CSRF 令牌
        _populate_global_request_state(request)
        _ensure_csrf_token(request)

        response = await call_next(request)
        return response
    finally:
        if request_db_gen is not None:
            try:
                request_db_gen.close()
            except Exception:
                pass

def get_page_config(db: Session, config_key: str, default_value: Any) -> Any:
    """
    获取页面显示配置
    
    Args:
        db: 数据库会话
        config_key: 配置键名
        default_value: 默认值
    
    Returns:
        配置值
    """
    setting = crud_setting.get_setting(db, key=config_key)
    return setting.value.get("value") if setting and setting.value else default_value


def _extract_metric_int(raw_value: Any, default: int = 0) -> int:
    if isinstance(raw_value, dict):
        raw_value = raw_value.get("value")
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _increment_post_views_metric(db: Session, post_id: int, step: int = 1) -> int:
    metric_key = f"post_views_count_{post_id}"
    db_setting = crud_setting.get_setting(db, key=metric_key)
    current_value = _extract_metric_int(db_setting.value if db_setting else 0, default=0)
    next_value = max(0, current_value + max(1, int(step or 1)))
    payload = {"value": next_value}

    if db_setting:
        crud_setting.update_setting(
            db,
            key=metric_key,
            setting_update=SettingUpdate(
                value=payload,
                description="Post views metric",
                category="post_metrics",
                type="integer",
            ),
        )
    else:
        crud_setting.create_setting(
            db,
            setting=SettingCreate(
                key=metric_key,
                value=payload,
                description="Post views metric",
                category="post_metrics",
                type="integer",
            ),
        )
    return next_value


def _sum_post_views_metrics(db: Session) -> int:
    total_views = 0
    rows = db.execute(
        select(Setting.value).where(Setting.key.like("post_views_count_%"))
    ).scalars().all()
    for row in rows:
        total_views += max(0, _extract_metric_int(row, default=0))
    return total_views


def _load_post_views_metrics_map(db: Session, post_ids: List[int], chunk_size: int = 300) -> Dict[int, int]:
    normalized_post_ids = sorted({int(post_id) for post_id in post_ids if isinstance(post_id, int) or str(post_id).isdigit()})
    if not normalized_post_ids:
        return {}

    views_map: Dict[int, int] = {}
    metric_keys = [f"post_views_count_{post_id}" for post_id in normalized_post_ids]
    batch_size = max(50, int(chunk_size or 300))

    for offset in range(0, len(metric_keys), batch_size):
        batch_keys = metric_keys[offset: offset + batch_size]
        try:
            rows = db.execute(
                select(Setting.key, Setting.value).where(Setting.key.in_(batch_keys))
            ).all()
        except Exception:
            continue

        for key, value in rows:
            key_text = str(key or "")
            if not key_text.startswith("post_views_count_"):
                continue
            suffix = key_text.replace("post_views_count_", "", 1)
            try:
                post_id = int(suffix)
            except (TypeError, ValueError):
                continue
            views_map[post_id] = max(0, _extract_metric_int(value, default=0))
    return views_map


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    return min(maximum, parsed)


def _parse_utc_datetime(raw_value: Any) -> Optional[datetime]:
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return None
    if raw_text.endswith("Z"):
        raw_text = f"{raw_text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_article_api_cache_dir() -> Path:
    cache_dir = (Path(settings.MEDIA_UPLOAD_DIR).resolve() / _ARTICLE_API_CACHE_DIR_NAME).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _load_article_api_cache_index(db: Session) -> Dict[str, Dict[str, Any]]:
    raw_cache = get_page_config(db, _ARTICLE_API_CACHE_INDEX_KEY, {})
    if not isinstance(raw_cache, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in raw_cache.items():
        if isinstance(key, str) and isinstance(value, dict):
            normalized[key] = value
    return normalized


def _upsert_runtime_setting(db: Session, key: str, value: Any, description: str) -> None:
    payload = {"value": value}
    db_setting = crud_setting.get_setting(db, key=key)
    if db_setting:
        crud_setting.update_setting(
            db,
            key=key,
            setting_update=SettingUpdate(value=payload),
        )
    else:
        crud_setting.create_setting(
            db,
            setting=SettingCreate(key=key, value=payload, description=description),
        )


def _cleanup_article_api_cache(
    cache_index: Dict[str, Dict[str, Any]],
    *,
    cache_dir: Path,
    now_utc: datetime,
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    cleaned_cache: Dict[str, Dict[str, Any]] = {}
    changed = False

    for cache_key, entry in cache_index.items():
        if not isinstance(entry, dict):
            changed = True
            continue

        file_name = str(entry.get("file_name", "") or "").strip()
        if not file_name:
            changed = True
            continue

        file_path = (cache_dir / file_name).resolve()
        if file_path.parent != cache_dir:
            changed = True
            continue

        expire_at = _parse_utc_datetime(entry.get("expire_at"))
        is_expired = expire_at is None or expire_at <= now_utc

        if is_expired or not file_path.exists():
            changed = True
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
            continue

        cleaned_cache[cache_key] = entry

    return cleaned_cache, changed


def _should_run_article_api_cache_cleanup(
    db: Session,
    *,
    now_utc: datetime,
    cleanup_interval_minutes: int,
) -> bool:
    last_cleanup_raw = get_page_config(db, _ARTICLE_API_CACHE_LAST_CLEANUP_KEY, "")
    last_cleanup_at = _parse_utc_datetime(last_cleanup_raw)
    if last_cleanup_at is None:
        return True
    elapsed_seconds = (now_utc - last_cleanup_at).total_seconds()
    return elapsed_seconds >= cleanup_interval_minutes * 60


def _guess_image_extension(content_type: str, final_url: str) -> str:
    mime_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/avif": ".avif",
        "image/svg+xml": ".svg",
    }
    normalized_type = str(content_type or "").split(";")[0].strip().lower()
    if normalized_type in mime_map:
        return mime_map[normalized_type]

    guessed_suffix = Path(urlparse(str(final_url or "")).path).suffix.lower()
    if guessed_suffix in _SUPPORTED_IMAGE_EXTENSIONS:
        return guessed_suffix
    return ".jpg"


def _build_article_api_cache_key(fallback_api_url: str, seed_value: str) -> str:
    return hashlib.sha256(f"{fallback_api_url}|{seed_value}".encode("utf-8")).hexdigest()


def _is_article_api_cached_url(image_url: str) -> bool:
    return str(image_url or "").startswith(_ARTICLE_API_CACHE_PUBLIC_PREFIX)


def _download_remote_image(remote_url: str) -> Optional[Tuple[bytes, str, str]]:
    try:
        request = UrlRequest(
            remote_url,
            headers={
                "User-Agent": "RewrZ/1.0 (+https://github.com/rewrz/RewrZ)",
                "Accept": "image/*,*/*;q=0.8",
            },
        )
        with urlopen(request, timeout=_ARTICLE_API_CACHE_HTTP_TIMEOUT_SECONDS) as response:
            content_type = str(response.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
            if not content_type.startswith("image/"):
                return None

            payload = response.read(_ARTICLE_API_CACHE_MAX_BYTES + 1)
            if len(payload) > _ARTICLE_API_CACHE_MAX_BYTES:
                return None

            final_url = str(response.geturl() or remote_url)
            return payload, content_type, final_url
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def _resolve_cached_remote_article_image(
    *,
    seed_value: str,
    fallback_api_url: str,
    cache_index: Dict[str, Dict[str, Any]],
    cache_ttl_minutes: int,
    cache_dir: Path,
    now_utc: datetime,
    download_if_missing: bool = True,
) -> Tuple[str, bool]:
    remote_url = _build_seeded_remote_image_url(fallback_api_url, seed_value)
    if not remote_url:
        return "", False

    cache_key = _build_article_api_cache_key(fallback_api_url, seed_value)
    existing_entry = cache_index.get(cache_key, {})
    if isinstance(existing_entry, dict):
        existing_file_name = str(existing_entry.get("file_name", "") or "").strip()
        existing_expire_at = _parse_utc_datetime(existing_entry.get("expire_at"))
        if existing_file_name and existing_expire_at and existing_expire_at > now_utc:
            existing_file_path = (cache_dir / existing_file_name).resolve()
            if existing_file_path.exists() and existing_file_path.parent == cache_dir:
                return f"{_ARTICLE_API_CACHE_PUBLIC_PREFIX}{existing_file_name}", False

    if not download_if_missing:
        return remote_url, False

    downloaded = _download_remote_image(remote_url)
    if not downloaded:
        return remote_url, False

    image_bytes, content_type, final_url = downloaded
    file_ext = _guess_image_extension(content_type, final_url)
    file_name = f"{cache_key}{file_ext}"
    file_path = (cache_dir / file_name).resolve()
    if file_path.parent != cache_dir:
        return remote_url, False

    old_file_name = str(existing_entry.get("file_name", "") or "").strip() if isinstance(existing_entry, dict) else ""
    if old_file_name and old_file_name != file_name:
        old_file_path = (cache_dir / old_file_name).resolve()
        if old_file_path.parent == cache_dir and old_file_path.exists():
            try:
                old_file_path.unlink()
            except OSError:
                pass

    temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
    try:
        with open(temp_path, "wb") as temp_file:
            temp_file.write(image_bytes)
        os.replace(temp_path, file_path)
    except OSError:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        return remote_url, False

    expire_at = now_utc + timedelta(minutes=cache_ttl_minutes)
    cache_index[cache_key] = {
        "file_name": file_name,
        "api_url": fallback_api_url,
        "seed": seed_value,
        "cached_at": now_utc.isoformat(),
        "expire_at": expire_at.isoformat(),
    }
    return f"{_ARTICLE_API_CACHE_PUBLIC_PREFIX}{file_name}", True


def _schedule_article_api_cache_prefetch(
    *,
    seed_value: str,
    fallback_api_url: str,
    cache_ttl_minutes: int,
) -> None:
    cache_key = _build_article_api_cache_key(fallback_api_url, seed_value)
    with _ARTICLE_API_CACHE_PREFETCH_LOCK:
        if cache_key in _ARTICLE_API_CACHE_PREFETCH_INFLIGHT:
            return
        _ARTICLE_API_CACHE_PREFETCH_INFLIGHT.add(cache_key)

    def _worker() -> None:
        try:
            db_manager.reload_if_needed()
            db = db_manager.get_session()
            if db is None:
                return

            try:
                cache_dir = _ensure_article_api_cache_dir()
                cache_index = _load_article_api_cache_index(db)
                now_utc = datetime.now(timezone.utc)

                _, changed = _resolve_cached_remote_article_image(
                    seed_value=seed_value,
                    fallback_api_url=fallback_api_url,
                    cache_index=cache_index,
                    cache_ttl_minutes=cache_ttl_minutes,
                    cache_dir=cache_dir,
                    now_utc=now_utc,
                    download_if_missing=True,
                )
                if changed:
                    _upsert_runtime_setting(
                        db,
                        _ARTICLE_API_CACHE_INDEX_KEY,
                        cache_index,
                        "Article fallback API cache index",
                    )
            finally:
                db.close()
        except Exception:
            # 后台预热失败不影响主请求
            pass
        finally:
            with _ARTICLE_API_CACHE_PREFETCH_LOCK:
                _ARTICLE_API_CACHE_PREFETCH_INFLIGHT.discard(cache_key)

    thread = threading.Thread(
        target=_worker,
        name=f"article-api-cache-{cache_key[:8]}",
        daemon=True,
    )
    thread.start()


def _resolve_posts_per_page(raw_value: Any, default_value: int, *, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = default_value
    parsed = max(minimum, parsed)
    return min(maximum, parsed)


def _normalize_list_navigation_mode(raw_value: Any) -> str:
    mode = str(raw_value or "pagination").strip().lower()
    return mode if mode in {"pagination", "infinite_scroll"} else "pagination"


def _normalize_article_fallback_source(raw_value: Any) -> str:
    source = str(raw_value or "local").strip().lower()
    return source if source in {"local", "api"} else "local"


def _resolve_article_fallback_local_dir(raw_value: Any) -> Optional[Path]:
    raw_path = str(raw_value or "").strip()
    if not raw_path:
        raw_path = _ARTICLE_FALLBACK_LOCAL_DIR_DEFAULT

    app_root = Path(__file__).resolve().parent
    repo_root = app_root.parent
    candidate = Path(raw_path).expanduser()
    candidates: List[Path]

    if candidate.is_absolute():
        candidates = [candidate]
    else:
        candidates = [
            repo_root / candidate,
            app_root / candidate,
        ]
        if not raw_path.startswith("rewrz/") and not raw_path.startswith("rewrz\\"):
            candidates.append(repo_root / "rewrz" / candidate)

    for dir_path in candidates:
        try:
            resolved = dir_path.resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_dir():
            return resolved
    return None


def _map_local_file_to_public_url(file_path: Path) -> Optional[str]:
    app_root = Path(__file__).resolve().parent
    static_root = (app_root / "static").resolve()
    media_root = Path(settings.MEDIA_UPLOAD_DIR).resolve()

    resolved = file_path.resolve()
    try:
        static_relative = resolved.relative_to(static_root)
        return f"/static/{static_relative.as_posix()}"
    except Exception:
        pass

    try:
        media_relative = resolved.relative_to(media_root)
        return f"/media/{media_relative.as_posix()}"
    except Exception:
        pass

    return None


def _collect_local_article_fallback_images(raw_dir: Any) -> List[str]:
    directory = _resolve_article_fallback_local_dir(raw_dir)
    if directory is None:
        return []

    image_urls: List[str] = []
    try:
        files = sorted(p for p in directory.rglob("*") if p.is_file())
    except Exception:
        return []

    for image_file in files:
        if image_file.suffix.lower() not in _SUPPORTED_IMAGE_EXTENSIONS:
            continue
        public_url = _map_local_file_to_public_url(image_file)
        if public_url:
            image_urls.append(public_url)
    return image_urls


def _build_seeded_remote_image_url(raw_api_url: Any, seed_value: str) -> str:
    api_url = str(raw_api_url or "").strip()
    if not api_url:
        return ""

    if "{seed}" in api_url:
        return api_url.replace("{seed}", quote(seed_value, safe=""))

    try:
        parsed = urlparse(api_url)
    except Exception:
        return ""

    if parsed.scheme not in {"http", "https"}:
        return ""

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query_items.append(("seed", seed_value))
    rebuilt = parsed._replace(query=urlencode(query_items))
    return urlunparse(rebuilt)


def _resolve_article_archive_cover_url(
    post: Post,
    *,
    fallback_source: str,
    fallback_api_url: str,
    fallback_local_images: List[str],
    remote_image_resolver: Optional[Callable[[str], str]] = None,
) -> str:
    featured_image_url = str(getattr(post, "featured_image_url", "") or "").strip()
    if featured_image_url and featured_image_url != "None":
        return featured_image_url

    rendered_html = get_effective_content_html(
        getattr(post, "content_markdown", ""),
        getattr(post, "content_html", ""),
    )
    content_images = extract_image_urls(rendered_html, featured_image_url=featured_image_url, max_count=1)
    if content_images:
        return content_images[0]

    seed_value = f"{getattr(post, 'id', 0)}-{getattr(post, 'slug', '')}"
    if fallback_source == "api":
        api_image = (
            remote_image_resolver(seed_value)
            if remote_image_resolver is not None
            else _build_seeded_remote_image_url(fallback_api_url, seed_value)
        )
        if api_image:
            return api_image

    if fallback_local_images:
        stable_hash = hashlib.sha256(seed_value.encode("utf-8")).hexdigest()
        index = int(stable_hash[:8], 16) % len(fallback_local_images)
        return fallback_local_images[index]

    if fallback_source != "api":
        return _build_seeded_remote_image_url(fallback_api_url, seed_value)

    return ""


def _attach_post_author_profiles(db: Session, posts: List[Post], *, fallback_name: str) -> None:
    if not posts:
        return
    profile_resolver = get_public_profile_resolver()
    fallback_display_name = str(fallback_name or "博主").strip() or "博主"

    for post in posts:
        author = getattr(post, "author", None)
        author_id = getattr(author, "id", None) if author is not None else getattr(post, "author_id", None)
        resolved_author_id: Optional[int] = None
        if author_id is not None:
            try:
                resolved_author_id = int(author_id)
            except (TypeError, ValueError):
                resolved_author_id = None
        author_profile = profile_resolver.resolve_author_profile(
            db,
            resolved_author_id,
            fallback_name=fallback_display_name,
        )
        setattr(post, "author_display_name", author_profile.get("display_name", fallback_display_name))
        setattr(post, "author_avatar_url", author_profile.get("avatar_url", "/static/images/default-avatar.png"))


def _build_public_pagination(
    page: int,
    total_count: int,
    page_size: int,
    url_builder: Callable[[int], str],
) -> tuple[int, dict]:
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 1
    current_page = max(1, min(page, total_pages))

    page_window_start = max(1, current_page - 2)
    page_window_end = min(total_pages, page_window_start + 4)
    page_window_start = max(1, page_window_end - 4)
    page_numbers = list(range(page_window_start, page_window_end + 1))

    pagination = {
        "current_page": current_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_count": total_count,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_url": url_builder(current_page - 1) if current_page > 1 else None,
        "next_url": url_builder(current_page + 1) if current_page < total_pages else None,
        "page_links": [{"page": p, "url": url_builder(p), "is_current": p == current_page} for p in page_numbers],
    }
    return current_page, pagination

def get_admin_path() -> str:
    """
    获取后台路径配置
    
    Returns:
        后台路径
    """
    return settings.ADMIN_PATH.rstrip('/')


@app.post("/api/v1/posts/{post_id}/unlock")
async def unlock_password_protected_post(
    request: Request,
    post_id: int,
    password: str = Form(...),
    next_url: str = Form("/"),
    db: Session = Depends(get_db),
):
    """
    验证密码保护内容访问密码并设置访问 Cookie
    """
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None or db_post.visibility != "password" or not db_post.password:
        raise HTTPException(status_code=404, detail="Post not found")

    safe_next_url = next_url if next_url and next_url.startswith("/") else "/"

    if not verify_password(password, db_post.password):
        context = build_base_template_context(request)
        context.update({
            "post": db_post,
            "next_url": safe_next_url,
            "error_message": "访问密码错误，请重试。",
        })
        return templates.TemplateResponse("password_protected.html", context, status_code=403)

    if safe_next_url == "/":
        if db_post.post_type == "page":
            safe_next_url = f"/{db_post.slug}"
        else:
            available_slugs = [fmt.slug for fmt in db_post.formats if getattr(fmt, "slug", None)] if db_post.formats else []
            primary_intent = choose_primary_intent_slug(available_slugs)
            path_segment = to_public_post_segment(primary_intent)
            safe_next_url = f"/{path_segment}/{db_post.slug}"

    response = RedirectResponse(url=safe_next_url, status_code=303)
    response.set_cookie(
        key=_get_post_access_cookie_name(post_id),
        value=_build_post_access_cookie_value(post_id, db_post.password),
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("rewrz/static/favicon.ico")




@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    首页路由
    
    显示最新的文章，数量根据后台配置确定，支持多重身份内容系统的格式优先级渲染，包含动态SEO元数据
    """
    page = max(1, int(page or 1))
    homepage_posts_limit = _resolve_posts_per_page(get_page_config(db, "homepage_posts_limit", 10), 10)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(Post.status == "published", Post.published_at.isnot(None))
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        homepage_posts_limit,
        lambda target_page: f"/?page={target_page}",
    )
    offset = (page - 1) * homepage_posts_limit
    posts = crud_post.get_posts(db, skip=offset, limit=homepage_posts_limit, status="published")

    # 首页时间轴封面：特色图 -> 正文首图 -> 随机二次元图（本地/在线）
    fallback_source = _normalize_article_fallback_source(
        get_page_config(db, "article_card_fallback_source", "local")
    )
    fallback_api_url = str(
        get_page_config(db, "article_card_fallback_api_url", _ARTICLE_FALLBACK_API_URL_DEFAULT)
        or _ARTICLE_FALLBACK_API_URL_DEFAULT
    ).strip()
    fallback_local_dir = get_page_config(db, "article_card_fallback_local_dir", _ARTICLE_FALLBACK_LOCAL_DIR_DEFAULT)
    api_cache_enabled = _parse_bool(
        get_page_config(db, "article_card_api_cache_enabled", _ARTICLE_API_CACHE_ENABLED_DEFAULT),
        _ARTICLE_API_CACHE_ENABLED_DEFAULT,
    )
    api_cache_ttl_minutes = _parse_bounded_int(
        get_page_config(db, "article_card_api_cache_ttl_minutes", _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT),
        _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT,
        5,
        10080,
    )
    api_cache_cleanup_minutes = _parse_bounded_int(
        get_page_config(db, "article_card_api_cache_cleanup_minutes", _ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT),
        _ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT,
        1,
        10080,
    )
    fallback_local_images = (
        _collect_local_article_fallback_images(fallback_local_dir)
        if fallback_source == "local"
        else []
    )
    api_cache_index: Dict[str, Dict[str, Any]] = {}
    api_cache_dir: Optional[Path] = None
    api_cache_changed = False
    now_utc = datetime.now(timezone.utc)

    if fallback_source == "api" and api_cache_enabled:
        api_cache_dir = _ensure_article_api_cache_dir()
        api_cache_index = _load_article_api_cache_index(db)
        if _should_run_article_api_cache_cleanup(
            db,
            now_utc=now_utc,
            cleanup_interval_minutes=api_cache_cleanup_minutes,
        ):
            api_cache_index, cleanup_changed = _cleanup_article_api_cache(
                api_cache_index,
                cache_dir=api_cache_dir,
                now_utc=now_utc,
            )
            api_cache_changed = api_cache_changed or cleanup_changed
            _upsert_runtime_setting(
                db,
                _ARTICLE_API_CACHE_LAST_CLEANUP_KEY,
                now_utc.isoformat(),
                "Article fallback API cache last cleanup time",
            )

    def resolve_cached_api_image(seed_value: str) -> str:
        nonlocal api_cache_changed
        if fallback_source != "api":
            return _build_seeded_remote_image_url(fallback_api_url, seed_value)
        if not api_cache_enabled or api_cache_dir is None:
            return _build_seeded_remote_image_url(fallback_api_url, seed_value)

        resolved_url, changed = _resolve_cached_remote_article_image(
            seed_value=seed_value,
            fallback_api_url=fallback_api_url,
            cache_index=api_cache_index,
            cache_ttl_minutes=api_cache_ttl_minutes,
            cache_dir=api_cache_dir,
            now_utc=now_utc,
            download_if_missing=False,
        )
        api_cache_changed = api_cache_changed or changed
        if not _is_article_api_cached_url(resolved_url):
            _schedule_article_api_cache_prefetch(
                seed_value=seed_value,
                fallback_api_url=fallback_api_url,
                cache_ttl_minutes=api_cache_ttl_minutes,
            )
        return resolved_url

    for post in posts:
        setattr(
            post,
            "homepage_cover_url",
            _resolve_article_archive_cover_url(
                post,
                fallback_source=fallback_source,
                fallback_api_url=fallback_api_url,
                fallback_local_images=fallback_local_images,
                remote_image_resolver=resolve_cached_api_image,
            ),
        )
    if fallback_source == "api" and api_cache_enabled and api_cache_changed:
        _upsert_runtime_setting(
            db,
            _ARTICLE_API_CACHE_INDEX_KEY,
            api_cache_index,
            "Article fallback API cache index",
        )
    profile_resolver = get_public_profile_resolver()
    site_profile = profile_resolver.resolve_homepage_profile(request, db)

    # 首页概览统计：分类、标签、评论、总浏览量
    homepage_stats = {
        "categories_count": crud_category.count_categories(db),
        "tags_count": crud_tag.count_tags(db),
        "comments_count": crud_comment.count_comments(db),
        "total_views": 0,
    }
    try:
        homepage_stats["total_views"] = _sum_post_views_metrics(db)
    except Exception:
        homepage_stats["total_views"] = 0
    
    # 获取首页SEO元数据
    from .api.seo import _generate_homepage_seo_data
    seo_data = _generate_homepage_seo_data(request, db)
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "posts": posts,
        "seo_data": seo_data,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
        "timeline_start_index": offset,
        "site_profile": site_profile,
        "homepage_stats": homepage_stats,
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/homepage_append.html", context)
    
    return templates.TemplateResponse("index.html", context)

# 聚合页面路由：统一使用 /formats/{format_slug}
# 注意：不要新增 /photos 等一级短路由，否则会与 /{page_slug} 动态页面路由冲突。
@app.get("/formats/{format_slug}", response_class=HTMLResponse)
async def format_page(request: Request, format_slug: str, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    内容类型归档页面（多重身份内容系统）
    
    根据内容类型 slug 显示对应文章，URL符合 /formats/{format_slug} 规范
    """
    format, resolved_slug = _resolve_format_by_slug(db, format_slug)
    if format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    page = max(1, int(page or 1))
    canonical_format_slug = resolved_slug or format_slug
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))
    exclude_format_ids: List[int] = []

    # /formats/article 仅展示“标准文章”，排除带 micro/poem 身份的内容
    if canonical_format_slug == "article":
        for excluded_slug in ("micro", "poem"):
            excluded_format = crud_format.get_format_by_slug(db, slug=excluded_slug)
            if excluded_format and excluded_format.id != format.id:
                exclude_format_ids.append(excluded_format.id)
    count_query = select(func.count(Post.id)).where(
        Post.formats.any(id=format.id),
        Post.status == "published",
        Post.published_at.isnot(None),
        Post.post_type.in_(["post", "article"]),
    )
    for excluded_format_id in exclude_format_ids:
        count_query = count_query.where(~Post.formats.any(id=excluded_format_id))

    total_posts_count = db.execute(count_query).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/formats/{canonical_format_slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_format(
        db,
        format_id=format.id,
        skip=offset,
        limit=archive_posts_limit,
        exclude_format_ids=exclude_format_ids,
    )
    from .models import Comment, ContentReaction

    post_ids = [item.id for item in posts if getattr(item, "id", None) is not None]
    comment_count_map = {}
    if post_ids:
        comment_rows = db.execute(
            select(Comment.post_id, func.count(Comment.id))
            .where(Comment.post_id.in_(post_ids), Comment.status == "approved")
            .group_by(Comment.post_id)
        ).all()
        comment_count_map = {pid: int(count or 0) for pid, count in comment_rows}
    for item in posts:
        setattr(item, "comment_count", int(comment_count_map.get(item.id, 0)))

    format_post_ids_query = select(Post.id).where(
        Post.formats.any(id=format.id),
        Post.status == "published",
        Post.published_at.isnot(None),
        Post.post_type.in_(["post", "article"]),
    )
    for excluded_format_id in exclude_format_ids:
        format_post_ids_query = format_post_ids_query.where(~Post.formats.any(id=excluded_format_id))

    micro_interaction_count = 0
    if canonical_format_slug == "micro":

        micro_comment_total = db.execute(
            select(func.count(Comment.id)).where(
                Comment.status == "approved",
                Comment.post_id.in_(format_post_ids_query),
            )
        ).scalar_one()
        micro_like_total = db.execute(
            select(func.count(ContentReaction.id)).where(
                ContentReaction.target_type == "post",
                ContentReaction.target_id.in_(format_post_ids_query),
                ContentReaction.like_active.is_(True),
            )
        ).scalar_one()
        micro_reaction_total = db.execute(
            select(func.count(ContentReaction.id)).where(
                ContentReaction.target_type == "post",
                ContentReaction.target_id.in_(format_post_ids_query),
                ContentReaction.reaction_type.isnot(None),
            )
        ).scalar_one()

        micro_interaction_count = int(
            (micro_comment_total or 0)
            + (micro_like_total or 0)
            + (micro_reaction_total or 0)
        )

    format_tag_topic_count = 0
    format_category_topic_count = 0
    format_hot_tags: List[Dict[str, Any]] = []
    if canonical_format_slug in {"micro", "poem", "article"}:
        from .models import Tag
        from .models.post import post_tags

        tag_post_rows = db.execute(
            select(
                Tag.id,
                Tag.name,
                Tag.slug,
                post_tags.c.post_id,
            )
            .join(post_tags, post_tags.c.tag_id == Tag.id)
            .where(post_tags.c.post_id.in_(format_post_ids_query))
        ).all()

        format_tag_topic_count = len({int(row.id) for row in tag_post_rows if getattr(row, "id", None) is not None})

        if tag_post_rows:
            tagged_post_ids = sorted(
                {
                    int(row.post_id)
                    for row in tag_post_rows
                    if getattr(row, "post_id", None) is not None
                }
            )
            tagged_post_ids_query = (
                select(post_tags.c.post_id)
                .where(post_tags.c.post_id.in_(format_post_ids_query))
                .group_by(post_tags.c.post_id)
            )

            tag_comment_rows = db.execute(
                select(Comment.post_id, func.count(Comment.id))
                .where(
                    Comment.status == "approved",
                    Comment.post_id.in_(tagged_post_ids_query),
                )
                .group_by(Comment.post_id)
            ).all()
            tag_like_rows = db.execute(
                select(ContentReaction.target_id, func.count(ContentReaction.id))
                .where(
                    ContentReaction.target_type == "post",
                    ContentReaction.target_id.in_(tagged_post_ids_query),
                    ContentReaction.like_active.is_(True),
                )
                .group_by(ContentReaction.target_id)
            ).all()
            tag_reaction_rows = db.execute(
                select(ContentReaction.target_id, func.count(ContentReaction.id))
                .where(
                    ContentReaction.target_type == "post",
                    ContentReaction.target_id.in_(tagged_post_ids_query),
                    ContentReaction.reaction_type.isnot(None),
                )
                .group_by(ContentReaction.target_id)
            ).all()

            tag_comment_map = {int(post_id): int(count or 0) for post_id, count in tag_comment_rows}
            tag_like_map = {int(post_id): int(count or 0) for post_id, count in tag_like_rows}
            tag_reaction_map = {int(post_id): int(count or 0) for post_id, count in tag_reaction_rows}
            tag_views_map = _load_post_views_metrics_map(db, tagged_post_ids)

            # 热门标签算法：浏览量 + 评论互动（评论/点赞/表态）综合加权
            view_weight = 1
            comment_weight = 30
            like_weight = 12
            reaction_weight = 10

            tag_heat_map: Dict[int, Dict[str, Any]] = {}
            for row in tag_post_rows:
                tag_id = int(row.id)
                post_id = int(row.post_id)
                comment_count = int(tag_comment_map.get(post_id, 0))
                like_count = int(tag_like_map.get(post_id, 0))
                reaction_count = int(tag_reaction_map.get(post_id, 0))
                view_count = int(tag_views_map.get(post_id, 0))

                interaction_score = (
                    comment_count * comment_weight
                    + like_count * like_weight
                    + reaction_count * reaction_weight
                )
                heat_score = interaction_score + view_count * view_weight

                current = tag_heat_map.get(tag_id)
                if current is None:
                    current = {
                        "id": tag_id,
                        "name": row.name,
                        "slug": row.slug,
                        "count": 0,
                        "heat_score": 0,
                        "interaction_score": 0,
                        "views_score": 0,
                    }
                    tag_heat_map[tag_id] = current

                current["count"] = int(current["count"]) + 1
                current["heat_score"] = int(current["heat_score"]) + int(heat_score)
                current["interaction_score"] = int(current["interaction_score"]) + int(interaction_score)
                current["views_score"] = int(current["views_score"]) + int(view_count)

            format_hot_tags = sorted(
                tag_heat_map.values(),
                key=lambda item: (
                    int(item.get("heat_score", 0)),
                    int(item.get("interaction_score", 0)),
                    int(item.get("views_score", 0)),
                    int(item.get("count", 0)),
                    -int(item.get("id", 0)),
                ),
                reverse=True,
            )[:10]

    if canonical_format_slug == "article":
        from .models.post import post_categories

        format_category_topic_count = int(
            db.execute(
                select(func.count(func.distinct(post_categories.c.category_id))).where(
                    post_categories.c.post_id.in_(format_post_ids_query)
                )
            ).scalar_one()
            or 0
        )

    profile_resolver = get_public_profile_resolver()
    format_profile = profile_resolver.resolve_format_profile(request, db, canonical_format_slug)
    _attach_post_author_profiles(db, posts, fallback_name=format_profile.get("display_name", "博主"))

    # /formats/article 使用图文卡片：特色图 -> 正文首图 -> 随机二次元图
    if canonical_format_slug == "article":
        fallback_source = _normalize_article_fallback_source(
            get_page_config(db, "article_card_fallback_source", "local")
        )
        fallback_api_url = str(
            get_page_config(db, "article_card_fallback_api_url", _ARTICLE_FALLBACK_API_URL_DEFAULT)
            or _ARTICLE_FALLBACK_API_URL_DEFAULT
        ).strip()
        fallback_local_dir = get_page_config(db, "article_card_fallback_local_dir", _ARTICLE_FALLBACK_LOCAL_DIR_DEFAULT)
        api_cache_enabled = _parse_bool(
            get_page_config(db, "article_card_api_cache_enabled", _ARTICLE_API_CACHE_ENABLED_DEFAULT),
            _ARTICLE_API_CACHE_ENABLED_DEFAULT,
        )
        api_cache_ttl_minutes = _parse_bounded_int(
            get_page_config(db, "article_card_api_cache_ttl_minutes", _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT),
            _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT,
            5,
            10080,
        )
        api_cache_cleanup_minutes = _parse_bounded_int(
            get_page_config(db, "article_card_api_cache_cleanup_minutes", _ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT),
            _ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT,
            1,
            10080,
        )
        fallback_local_images = (
            _collect_local_article_fallback_images(fallback_local_dir)
            if fallback_source == "local"
            else []
        )
        api_cache_index: Dict[str, Dict[str, Any]] = {}
        api_cache_dir: Optional[Path] = None
        api_cache_changed = False
        now_utc = datetime.now(timezone.utc)

        if fallback_source == "api" and api_cache_enabled:
            api_cache_dir = _ensure_article_api_cache_dir()
            api_cache_index = _load_article_api_cache_index(db)
            if _should_run_article_api_cache_cleanup(
                db,
                now_utc=now_utc,
                cleanup_interval_minutes=api_cache_cleanup_minutes,
            ):
                api_cache_index, cleanup_changed = _cleanup_article_api_cache(
                    api_cache_index,
                    cache_dir=api_cache_dir,
                    now_utc=now_utc,
                )
                api_cache_changed = api_cache_changed or cleanup_changed
                _upsert_runtime_setting(
                    db,
                    _ARTICLE_API_CACHE_LAST_CLEANUP_KEY,
                    now_utc.isoformat(),
                    "Article fallback API cache last cleanup time",
                )

        def resolve_cached_api_image(seed_value: str) -> str:
            nonlocal api_cache_changed
            if fallback_source != "api":
                return _build_seeded_remote_image_url(fallback_api_url, seed_value)
            if not api_cache_enabled or api_cache_dir is None:
                return _build_seeded_remote_image_url(fallback_api_url, seed_value)

            resolved_url, changed = _resolve_cached_remote_article_image(
                seed_value=seed_value,
                fallback_api_url=fallback_api_url,
                cache_index=api_cache_index,
                cache_ttl_minutes=api_cache_ttl_minutes,
                cache_dir=api_cache_dir,
                now_utc=now_utc,
                download_if_missing=False,
            )
            api_cache_changed = api_cache_changed or changed
            if not _is_article_api_cached_url(resolved_url):
                _schedule_article_api_cache_prefetch(
                    seed_value=seed_value,
                    fallback_api_url=fallback_api_url,
                    cache_ttl_minutes=api_cache_ttl_minutes,
                )
            return resolved_url

        for post in posts:
            setattr(
                post,
                "archive_cover_url",
                _resolve_article_archive_cover_url(
                    post,
                    fallback_source=fallback_source,
                    fallback_api_url=fallback_api_url,
                    fallback_local_images=fallback_local_images,
                    remote_image_resolver=resolve_cached_api_image,
                ),
            )
        if fallback_source == "api" and api_cache_enabled and api_cache_changed:
            _upsert_runtime_setting(
                db,
                _ARTICLE_API_CACHE_INDEX_KEY,
                api_cache_index,
                "Article fallback API cache index",
            )
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "format": format,
        "format_slug": canonical_format_slug,  # 将实际slug传递给模板
        "posts": posts,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
        "format_profile": format_profile,
        "micro_interaction_count": micro_interaction_count,
        "format_tag_topic_count": format_tag_topic_count,
        "format_category_topic_count": format_category_topic_count,
        "format_hot_tags": format_hot_tags,
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/format_archive_append.html", context)
    
    return templates.TemplateResponse("format_archive.html", context)


@app.get("/archives/media/{media_slug}", response_class=HTMLResponse)
async def posts_by_media_attachment(request: Request, media_slug: str, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    按媒体附件类型聚合页面

    注意：使用 /archives/media/{media_slug}，避免与 /media 静态目录冲突。
    """
    normalized_media_slug = (media_slug or "").strip().lower()
    registered_media_keys = set(list_registered_media_attachment_keys())
    if normalized_media_slug not in registered_media_keys:
        raise HTTPException(status_code=404, detail="Media attachment type not found")

    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))

    posts = crud_post.get_archive_posts(db)
    matched_posts = []

    for post in posts:
        rendered_content = get_effective_content_html(post.content_markdown, post.content_html)
        summary = summarize_media_attachments(
            rendered_content,
            featured_image_url=post.featured_image_url,
        )
        media_flags = detect_media_flags(summary)
        if not media_flags.get(normalized_media_slug, False):
            continue

        summary_dict = summary.to_dict()
        setattr(post, "media_attachment_summary", summary_dict)
        setattr(post, "media_flags", media_flags)
        setattr(post, "all_image_urls", list(summary.image_urls))
        primary_link = summary.external_links[0] if summary.external_links else ""
        setattr(post, "media_primary_external_link", primary_link)
        setattr(post, "media_primary_external_domain", urlparse(primary_link).netloc if primary_link else "")
        matched_posts.append(post)

    total_matched_count = len(matched_posts)
    page, pagination = _build_public_pagination(
        page,
        total_matched_count,
        archive_posts_limit,
        lambda target_page: f"/archives/media/{normalized_media_slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    matched_posts = matched_posts[offset: offset + archive_posts_limit]
    _attach_post_author_profiles(
        db,
        matched_posts,
        fallback_name=str(getattr(request.state, "site_title", "博主") or "博主"),
    )

    media_nav_items = get_default_media_navigation()
    selected_media_item = next(
        (item for item in media_nav_items if item.get("key") == normalized_media_slug),
        {"key": normalized_media_slug, "name": normalized_media_slug, "icon": "fa-photo-film"},
    )

    context = build_base_template_context(request)
    context.update({
        "media_slug": normalized_media_slug,
        "media_item": selected_media_item,
        "media_nav_items": media_nav_items,
        "posts": matched_posts,
        "total_count": total_matched_count,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
    })
    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/media_archive_append.html", context)
    return templates.TemplateResponse("media_archive.html", context)

@app.get("/archives/by-category/{category_slug}", response_class=HTMLResponse)
async def posts_by_category(request: Request, category_slug: str, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    按分类归档页面
    
    显示指定分类下的所有文章
    """
    category = crud_category.get_category_by_slug(db, slug=category_slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(
            Post.categories.any(id=category.id),
            Post.status == "published",
            Post.published_at.isnot(None),
            Post.post_type.in_(["post", "article"]),
        )
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/by-category/{category.slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_category(
        db,
        category_id=category.id,
        skip=offset,
        limit=archive_posts_limit,
    )
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "category": category,
        "posts": posts,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/category_archive_append.html", context)
    
    return templates.TemplateResponse("category_archive.html", context)

@app.get("/archives/by-tag/{tag_slug}", response_class=HTMLResponse)
async def posts_by_tag(request: Request, tag_slug: str, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    按标签归档页面
    
    显示指定标签下的所有文章
    """
    tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(
            Post.tags.any(id=tag.id),
            Post.status == "published",
            Post.published_at.isnot(None),
            Post.post_type.in_(["post", "article"]),
        )
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/by-tag/{tag.slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_tag(
        db,
        tag_id=tag.id,
        skip=offset,
        limit=archive_posts_limit,
    )
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "tag": tag,
        "posts": posts,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/tag_archive_append.html", context)
    
    return templates.TemplateResponse("tag_archive.html", context)

@app.get("/archives/{year}/{month}", response_class=HTMLResponse)
async def posts_by_month(request: Request, year: int, month: int, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    """
    按年月归档页面
    
    显示指定年月的所有文章
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=404, detail="Invalid month")

    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))

    all_posts = crud_post.get_posts_by_year_month(db, year=year, month=month)
    total_posts_count = len(all_posts)
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/{year}/{month}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = all_posts[offset: offset + archive_posts_limit]
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "year": year,
        "month": month,
        "posts": posts,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return templates.TemplateResponse("fragments/monthly_archive_append.html", context)
    
    return templates.TemplateResponse("monthly_archive.html", context)

@app.get("/archives", response_class=HTMLResponse)
async def archives_page(
    request: Request,
    page: int = 1,
    append: int = 0,
    append_view: str = "yearly",
    db: Session = Depends(get_db),
):
    """
    总归档页面
    
    显示所有文章的归档列表
    """
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_posts_per_page(get_page_config(db, "archive_posts_limit", 20), 20, maximum=200)
    list_navigation_mode = _normalize_list_navigation_mode(get_page_config(db, "list_navigation_mode", "pagination"))
    total_posts_count = db.execute(
        select(func.count(Post.id)).where(
            Post.status == "published",
            Post.published_at.isnot(None),
            Post.post_type.in_(["post", "article"]),
        )
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_archive_posts_paginated(
        db,
        skip=offset,
        limit=archive_posts_limit,
    )
    
    # 构建模板上下文（现在包含统一的设置数据）
    context = build_base_template_context(request)
    context.update({
        "posts": posts,
        "pagination": pagination,
        "list_navigation_mode": list_navigation_mode,
        "append_view": append_view if append_view in {"yearly", "monthly"} else "yearly",
    })

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        if context["append_view"] == "monthly":
            return templates.TemplateResponse("fragments/archives_monthly_append.html", context)
        return templates.TemplateResponse("fragments/archives_yearly_append.html", context)
    
    return templates.TemplateResponse("archives.html", context)

# 统一注册全局异常处理器（集中管理，降低重复与维护成本）
error_handler.register_error_handlers(app)

# 为CSRF保护添加会话中间件
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# 添加设置加载中间件（在会话中间件之后）
app.add_middleware(SettingsMiddleware)
