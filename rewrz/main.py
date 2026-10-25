"""
RewrZ 博客系统主应用模块

基于FastAPI构建的个人博客系统，支持多重身份内容系统、动态主题、
反垃圾评论、版本快照等功能。采用HTMX + Tailwind CSS前端技术栈。
"""
import os
import hashlib
import mimetypes
import threading
import time
import asyncio
from io import BytesIO
from math import ceil
from PIL import Image
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote, urlsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError, HTTPError
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File, BackgroundTasks, Header, Body
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI
from contextlib import asynccontextmanager
import json
from sqlalchemy.orm import Session
from .core.template_filters import get_templates  # 导入带过滤器的模板系统
from .core.template_context import build_base_template_context, HOMEPAGE_SETTING_KEYS, DEFAULT_HOMEPAGE_SETTINGS, DEFAULT_BASE_SETTINGS
from .core.database import get_db, create_all_tables, db_manager
from .core.config import get_env_file_path, settings  # 导入settings实例
from .schemas import UserCreate, User, PostCreate, PostUpdate, SettingCreate, SettingUpdate
from .crud import user as crud_user
from .core.security import get_current_user, verify_password, decode_access_token, is_user_token_payload_valid, should_use_secure_cookie  # 导入安全函数
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
from .api import media_settings as media_settings_api # 导入媒体设置路由
from .api import captcha as captcha_api # 导入验证码API路由
from .api import admin_routes as admin_routes_api
from .api import external as external_api
from .api import public_pages as public_pages_api
from .api import traffic_beacon as traffic_beacon_api
from .core.public_profile import get_public_profile_resolver
from .core.admin_security import should_run_login_audit_auto_cleanup, run_login_audit_auto_cleanup
from .crud import post as crud_post
from .crud import comment as crud_comment
from .crud import reaction as crud_reaction
from .crud import setting as crud_setting # Import crud_setting
from .crud import format as crud_format # 导入格式CRUD模块以修复未定义变量错误
from .models import Post, Setting
from .core import error_handler  # 导入错误处理模块
from .core import public_list_cache  # 公共列表页缓存：匿名列表页跳过 CSRF 会话创建
from .core import public_detail_cache  # 公开详情页整页缓存（CSRF 占位符替换）
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from sqlalchemy import select, func
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from datetime import date, datetime, timedelta, timezone # 导入date和datetime用于纪念日检查和主题调度
from .core.session_middleware import RequestAwareSessionMiddleware # 导入按请求判定的会话中间件
from .core.security import generate_csrf_token # 导入CSRF令牌生成函数
from .core.settings_middleware import SettingsMiddleware # 导入设置中间件
from .core.admin_path import get_admin_path
from .core.request_context import REQUEST_ID_HEADER, ensure_request_id, install_access_log_redaction_filter, redact_url_for_log
from .core.task_scheduler import default_task_scheduler
from .core import traffic_analytics
from .core import request_guard  # 垃圾爬虫与扫描路径拦截（最外层，先于会话与数据库）
from .core import post_views  # 浏览量内存计数，后台批量落库
from .core.content_access import (
    build_post_access_cookie_value,
    count_hide_blocks,
    get_comment_unlock_cookie_name,
    get_post_access_cookie_name,
    has_hide_blocks,
    has_valid_password_cookie,
    render_markdown_with_hide_blocks,
    strip_hide_blocks,
)
from .core.toc import build_toc_from_html
from .core.time_utils import utc_now_naive
from .core.content_utils import get_effective_content_html
from .core.micro_text import enhance_micro_html
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
from .core.page_templates import (
    DEFAULT_PAGE_TEMPLATE,
    normalize_page_template,
    resolve_page_template_file,
)

# 全局状态，用于标记后台路由是否已注册
ADMIN_ROUTES_REGISTERED = False

install_access_log_redaction_filter()


def register_default_scheduled_tasks() -> None:
    """
    注册项目默认定时任务。

    当前先接入节日特效引擎需要的两个核心任务，后续其他模块
    直接继续向统一调度器注册即可。
    """
    registered = default_task_scheduler.get_registered_tasks()
    if "effects_daily_refresh" not in registered:
        default_task_scheduler.register_daily_task(
            name="effects_daily_refresh",
            hour=0,
            minute=0,
            second=0,
            handler=themes_api.run_daily_effects_refresh_task,
            description="每日凌晨重算当前节日特效结果并清理过期状态",
        )

    if "public_holiday_rollover" not in registered:
        default_task_scheduler.register_yearly_task(
            name="public_holiday_rollover",
            month=12,
            day=31,
            hour=0,
            minute=0,
            second=0,
            handler=themes_api.run_public_holiday_rollover_task,
            description="每年 12 月 31 日凌晨重建下一年公共节日清单",
        )

    if "login_audit_auto_cleanup" not in registered:
        default_task_scheduler.register_interval_task(
            name="login_audit_auto_cleanup",
            interval_seconds=1800,
            handler=run_login_audit_auto_cleanup_task,
            description="按安全中心配置自动清理过期登录审计记录",
        )

    if "traffic_analytics_cleanup" not in registered:
        default_task_scheduler.register_daily_task(
            name="traffic_analytics_cleanup",
            hour=0,
            minute=20,
            second=0,
            handler=run_traffic_analytics_cleanup_task,
            description="每日清理过期访问统计聚合数据",
        )


async def run_traffic_analytics_cleanup_task() -> int:
    """异步清理包装：数据库操作放到线程，避免阻塞事件循环。"""
    result = await asyncio.to_thread(traffic_analytics.cleanup_traffic_data)
    return sum(int(value or 0) for value in (result or {}).values())


def run_login_audit_auto_cleanup_task() -> int:
    session = db_manager.get_session()
    if session is None:
        return 0

    try:
        if not should_run_login_audit_auto_cleanup(session):
            return 0
        return run_login_audit_auto_cleanup(session)
    finally:
        session.close()

# 应用生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时检查.env文件，如果不存在则重定向到安装向导
    if not os.path.exists(get_env_file_path()):
        print("INFO: .env file not found. Redirecting to installer.")
        # 这不会立即重定向，但会为根路由设置条件
    create_all_tables()
    register_default_scheduled_tasks()
    await default_task_scheduler.start()
    await traffic_analytics.start_flush_loop()
    post_views.start_post_views_flusher()
    yield
    # 关闭时先做最后一次统计刷写，再停止任务调度器
    post_views.stop_post_views_flusher()
    await traffic_analytics.stop_flush_loop()
    await default_task_scheduler.stop()

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

class CacheControlStaticFiles(StaticFiles):
    """给静态文件补上 Cache-Control。

    模板里的静态资源链接都带 `?v=<文件时间戳>`，URL 变化即代表内容变化，
    因此可以放心长期缓存；否则浏览器每次导航都要重新下载全部 CSS/JS/字体，
    首屏会一直被这些重复请求拖住。
    """

    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        query = (scope.get("query_string") or b"").decode("latin-1")
        if "v=" in query:
            # 模板输出的静态资源都带 ?v=<文件时间戳>，URL 变了内容才变，可以长期强缓存
            response.headers.setdefault("Cache-Control", self.cache_control)
        else:
            # 用户可能替换的图片等没有版本参数的资源只缓存 1 小时，避免换图后长期看不到更新
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response


# Windows 注册表经常缺少 webp/avif 的 MIME 登记，若不显式补登记，
# 封面缓存会以 application/octet-stream 返回，部分浏览器会拒绝渲染缩略图。
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")

# 挂载静态文件目录（URL 带版本号，可长期强缓存）
app.mount(
    "/static",
    CacheControlStaticFiles(
        directory="rewrz/static",
        cache_control="public, max-age=31536000, immutable",
    ),
    name="static",
)

# 配置Jinja2模板引擎（带自定义过滤器）
templates = get_templates()

_ARTICLE_FALLBACK_API_URL_DEFAULT = "https://www.loliapi.com/acg/"
_ARTICLE_FALLBACK_LOCAL_DIR_DEFAULT = "rewrz/static/images/anime/random"
_SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".svg"}
_ARTICLE_API_CACHE_DIR_NAME = "article-fallback-cache"
_ARTICLE_API_CACHE_INDEX_KEY = "article_card_api_cache_index"
_ARTICLE_API_CACHE_LAST_CLEANUP_KEY = "article_card_api_cache_last_cleanup_at"
_ARTICLE_API_CACHE_ENABLED_DEFAULT = True
# 0 表示永不过期：封面首次抓取后会一直复用本地文件，只有编辑文章或手动刷新才重建
_ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT = 0
_ARTICLE_API_CACHE_TTL_MINUTES_MAX = 525600
_ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT = 120
_ARTICLE_API_CACHE_MAX_BYTES = 8 * 1024 * 1024
_ARTICLE_API_CACHE_MAX_WIDTH = 1280
_ARTICLE_API_CACHE_MAX_PIXELS = 12_000_000
_ARTICLE_API_CACHE_WEBP_QUALITY = 78
_ARTICLE_API_CACHE_HTTP_TIMEOUT_SECONDS = 8
_ARTICLE_API_CACHE_PUBLIC_PREFIX = f"/media/{_ARTICLE_API_CACHE_DIR_NAME}/"
_ARTICLE_API_CACHE_PREFETCH_INFLIGHT: set[str] = set()
_ARTICLE_API_CACHE_PREFETCH_LOCK = threading.Lock()
# 后台封面预取同时只处理少量图片，避免列表页一次性下载 + 解码大量封面把内存打满
_ARTICLE_API_CACHE_PREFETCH_MAX_CONCURRENCY = 2
_ARTICLE_API_CACHE_PREFETCH_SEMAPHORE = threading.BoundedSemaphore(
    _ARTICLE_API_CACHE_PREFETCH_MAX_CONCURRENCY
)
_ARTICLE_FALLBACK_LOCAL_CACHE_TTL_SECONDS = 300
_ARTICLE_FALLBACK_LOCAL_CACHE: dict[str, tuple[float, tuple[str, ...]]] = {}
_ARTICLE_FALLBACK_LOCAL_CACHE_LOCK = threading.Lock()


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
        db_user = crud_user.get_user(db, user_id=int(user_id))
        return is_user_token_payload_valid(db_user, payload)
    except (TypeError, ValueError):
        return False


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
    admin_routes_api.register_admin_primary_routes(
        app,
        templates=templates,
        default_base_settings=DEFAULT_BASE_SETTINGS,
        default_homepage_settings=DEFAULT_HOMEPAGE_SETTINGS,
        article_api_cache_enabled_default=_ARTICLE_API_CACHE_ENABLED_DEFAULT,
        article_api_cache_ttl_minutes_default=_ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT,
        article_api_cache_cleanup_minutes_default=_ARTICLE_API_CACHE_CLEANUP_MINUTES_DEFAULT,
    )

    @app.get("/authors/{username}")
    def read_author_profile_entry(username: str, db: Session = Depends(get_db)):
        """
        站内作者入口（最小实现）。
        仅校验用户存在后跳转微博聚合页，作为 @提及 的稳定站内链接。
        """
        normalized_username = str(username or "").strip()
        if not normalized_username:
            raise HTTPException(status_code=404, detail="Author not found")
        db_user = crud_user.get_user_by_username(db, normalized_username)
        if db_user is None:
            db_user = crud_user.get_user_by_username(db, normalized_username.lower())
        if db_user is None:
            raise HTTPException(status_code=404, detail="Author not found")
        return RedirectResponse(url="/formats/micro", status_code=302)

    @app.get("/{format_slug}/{post_slug}", response_class=HTMLResponse)
    def read_post(request: Request, format_slug: str, post_slug: str, db: Session = Depends(get_db)):
        """
        文章详情页路由
        
        根据文章别名显示单篇文章的详细内容，包含动态SEO元数据
        """
        # 扫描器的随机路径不必进入数据库查询
        if not request_guard.is_reasonable_slug(post_slug) or not request_guard.is_reasonable_slug(format_slug):
            raise HTTPException(status_code=404, detail="Post not found")

        # 渲染前记录缓存版本：渲染期间发生写操作时，本次结果不会写入缓存
        detail_cache_version = public_detail_cache.get_public_detail_cache_version()

        db_post = crud_post.get_post_by_slug(db, slug=post_slug)
        is_admin = _is_admin_authenticated(request, db)

        if db_post is None or db_post.post_type == "page" or (db_post.status != "published" and not is_admin):
            raise HTTPException(status_code=404, detail="Post not found")

        # 发布时间在未来的已发布内容视为定时发布，未到时间仅管理员可预览
        if (
            not is_admin
            and db_post.published_at is not None
            and db_post.published_at > utc_now_naive()
        ):
            raise HTTPException(status_code=404, detail="Post not found")

        # 私密内容仅管理员可访问
        if db_post.visibility == "private" and not is_admin:
            raise HTTPException(status_code=404, detail="Post not found")

        # 密码保护内容：未通过验证时展示密码输入页
        if db_post.visibility == "password" and not is_admin and not has_valid_password_cookie(request, db_post):
            context = build_base_template_context(request)
            context.update({
                "post": db_post,
                "next_url": request.url.path,
                "error_message": None,
            })
            return templates.TemplateResponse(request, "password_protected.html", context, status_code=401)
        
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

        # 访问即计数：只累加内存，后台线程每 15 秒批量落库，避免每个 PV 都写库
        post_views.increment_post_views(db_post.id)
        
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
        if active_format_slug == "micro":
            display_content_html = enhance_micro_html(display_content_html, db)

        # 自动目录（TOC）：达到阈值时生成
        display_content_html, toc_items = build_toc_from_html(display_content_html, min_headings=3)
        profile_resolver = get_public_profile_resolver()
        format_profile = profile_resolver.resolve_format_profile(request, db, active_format_slug)
        _attach_post_author_profiles(db, [db_post], fallback_name=format_profile.get("display_name", "博主"))
        _attach_article_cover_urls(db, [db_post], attr_name="detail_cover_url")
        related_articles: List[Post] = []
        try:
            from .core.blog_enhancements import get_related_posts as get_enhanced_related_posts

            related_limit = _resolve_posts_per_page(
                get_page_config(db, "related_posts_limit", 5),
                5,
                minimum=1,
                maximum=20,
            )
            related_articles = get_enhanced_related_posts(db, db_post, related_limit)
            _attach_article_cover_urls(db, related_articles, attr_name="related_cover_url")
        except Exception:
            related_articles = []

        # 构建模板上下文（现在包含统一的设置数据）
        context = build_base_template_context(request)
        context.update({
            "db": db,
            "post": db_post,
            "seo_data": seo_data,
            "donation_config": donation_config,
            "display_content_html": display_content_html,
            "toc_items": toc_items,
            "active_format_slug": active_format_slug,
            "format_profile": format_profile,
            "related_articles": related_articles,
            "page_background_image_url": getattr(db_post, "detail_cover_url", "") or "",
        })
        context.update(_build_comment_view_context(db, db_post, request))
        
        response = templates.TemplateResponse(request, "post_detail.html", context)
        public_detail_cache.store_public_detail_response(
            request, response, version=detail_cache_version, content_id=db_post.id
        )
        public_detail_cache.apply_public_detail_cache_headers(response)
        return response

    # 动态页面路由处理器
    @app.get("/{page_slug}", response_class=HTMLResponse)
    def read_page(request: Request, page_slug: str, db: Session = Depends(get_db)):
        """
        页面详情页路由
        
        根据页面别名显示单个页面的详细内容
        """
        # 扫描器的随机路径不必进入保留字判断与数据库查询
        if not request_guard.is_reasonable_slug(page_slug):
            raise HTTPException(status_code=404, detail="Page not found")

        # 渲染前记录缓存版本：渲染期间发生写操作时，本次结果不会写入缓存
        detail_cache_version = public_detail_cache.get_public_detail_cache_version()

        # 屏蔽框架保留入口和后台保留 slug，避免误落到普通页面查询。
        reserved_page_slugs = {
            "installer",
            "static",
            "api",
            "favicon.ico",
            "settings",
            "error-settings",
            "comment-settings",
            "security-center",
            "data-management",
            "system-info",
            "dashboard",
            "users",
            "posts",
            "pages",
            "categories",
            "tags",
            "media",
            "themes",
            "api-keys",
        }
        admin_root_slug = get_admin_path().strip("/").split("/", 1)[0]
        if admin_root_slug:
            reserved_page_slugs.add(admin_root_slug)
        if page_slug in reserved_page_slugs:
            raise HTTPException(status_code=404, detail="Page not found")
        
        is_admin = _is_admin_authenticated(request, db)

        # 检查是否存在具有该别名的页面
        db_page = crud_post.get_post_by_slug(db, slug=page_slug)
        if db_page is None or db_page.post_type != "page" or (db_page.status != "published" and not is_admin):
            # 如果没有找到页面，检查是否是其他特殊路由
            raise HTTPException(status_code=404, detail="Page not found")

        # 发布时间在未来的已发布页面视为定时发布，未到时间仅管理员可预览
        if (
            not is_admin
            and db_page.published_at is not None
            and db_page.published_at > utc_now_naive()
        ):
            raise HTTPException(status_code=404, detail="Page not found")

        # 私密页面仅管理员可访问
        if db_page.visibility == "private" and not is_admin:
            raise HTTPException(status_code=404, detail="Page not found")

        # 密码保护页面：未验证则返回密码输入页
        if db_page.visibility == "password" and not is_admin and not has_valid_password_cookie(request, db_page):
            context = build_base_template_context(request)
            context.update({
                "post": db_page,
                "next_url": request.url.path,
                "error_message": None,
            })
            return templates.TemplateResponse(request, "password_protected.html", context, status_code=401)

        # 访问即计数：只累加内存，后台线程每 15 秒批量落库，避免每个 PV 都写库
        post_views.increment_post_views(db_page.id)
        
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
        _attach_article_cover_urls(db, [db_page], attr_name="detail_cover_url")
        
        # 构建模板上下文（现在包含统一的设置数据）
        context = build_base_template_context(request)
        selected_page_template = normalize_page_template(getattr(db_page, "page_template", DEFAULT_PAGE_TEMPLATE))
        context.update({
            "db": db,
            "post": db_page,
            "seo_data": seo_data,
            "display_content_html": display_content_html,
            "toc_items": toc_items,
            "selected_page_template": selected_page_template,
            "page_background_image_url": getattr(db_page, "detail_cover_url", "") or "",
        })
        context.update(_build_comment_view_context(db, db_page, request))

        response = templates.TemplateResponse(request, resolve_page_template_file(selected_page_template), context)
        public_detail_cache.store_public_detail_response(
            request, response, version=detail_cache_version, content_id=db_page.id
        )
        public_detail_cache.apply_public_detail_cache_headers(response)
        return response

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
app.include_router(external_api.router)
# 包含验证码API路由
app.include_router(captcha_api.router)
# 包含公开页面访问上报路由
app.include_router(traffic_beacon_api.router)
# 抽取：构建全局请求上下文（初始化默认值、读取设置、主题调度/纪念日、后台路径）
def _populate_global_request_state(request: Request) -> None:
    # 初始化全局上下文变量
    request.state.effect_body_class = ""
    request.state.current_effect_scene = None
    request.state.current_effects = []
    request.state.effects_source = "none"
    request.state.current_theme = "light"
    request.state.current_theme_source = "site_default"
    request.state.theme_variables = {}
    request.state.glass_intensity = "medium"
    request.state.background_image_settings = {"type": "none", "custom_url": None}
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
        settings_keys.update({
            "current_theme": "light",
            "glass_intensity": "medium",
            "background_image_settings": {"type": "none", "custom_url": None},
        })
        all_settings = crud_setting.get_settings_by_keys(db, list(settings_keys.keys()))
        for key, default_value in settings_keys.items():
            setattr(request.state, key, all_settings.get(key, default_value))
        resolved_theme = themes_api.resolve_active_theme(db, request=request)
        resolved_effects = themes_api.resolve_active_effects(db)
        request.state.current_theme = resolved_theme["theme_id"]
        request.state.current_theme_source = resolved_theme["theme_source"]
        # 后台与认证页模板直接内联该变量表，避免首屏再发一次阻塞请求
        request.state.theme_variables = resolved_theme["variables"]
        request.state.glass_intensity = resolved_theme["glass_intensity"]
        request.state.background_image_settings = resolved_theme["background"]
        request.state.current_effect_scene = resolved_effects["scene"]
        request.state.current_effects = resolved_effects["effects"]
        request.state.effects_source = resolved_effects["source"]
        request.state.effect_body_class = resolved_effects["body_classes"][0] if resolved_effects["body_classes"] else ""
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

def _request_host_name(request: Request) -> str:
    """从 Host 头提取小写主机名（自动去掉端口）。"""
    raw_host = str(request.headers.get("host") or "").strip()
    if not raw_host:
        return ""
    try:
        return str(urlsplit(f"//{raw_host}").hostname or "").lower()
    except ValueError:
        return ""


def _is_allowed_request_host(request: Request) -> bool:
    """按 ALLOWED_HOSTS 白名单校验 Host，为空时保持旧行为。"""
    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", []) or []
    if not allowed_hosts:
        return True
    if "*" in allowed_hosts:
        return True

    host = _request_host_name(request)
    if not host:
        return False
    for item in allowed_hosts:
        normalized = str(item or "").strip().lower()
        if not normalized:
            continue
        if normalized.startswith("."):
            suffix = normalized.lstrip(".")
            if host == suffix or host.endswith("." + suffix):
                return True
        elif host == normalized:
            return True
    return False


@app.middleware("http")
async def add_global_context(request: Request, call_next):
    global ADMIN_ROUTES_REGISTERED
    request_id = ensure_request_id(request)

    def attach_request_id(response):
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        return response

    if not _is_allowed_request_host(request):
        return attach_request_id(PlainTextResponse("非法的主机头", status_code=400))

    # 文件类请求（静态资源、媒体文件）不需要数据库会话、CSRF 与全局设置。
    # 跳过可以避免每个文件请求都查一遍数据库，也避免响应被追加 Set-Cookie / Vary: Cookie
    # 而破坏浏览器与 CDN 的缓存。
    if request.url.path.startswith(("/static/", "/media/")):
        return await call_next(request)

    # 动态注册后台路由（如果需要）
    # 在安装完成后，通过首次请求动态加载后台路由，避免重启服务器
    if settings.installation_complete and not ADMIN_ROUTES_REGISTERED:
        register_admin_routes()
        ADMIN_ROUTES_REGISTERED = True

    # 安装完成后，不再暴露 installer 路径，避免通过重定向等方式泄露后台入口信息
    if settings.installation_complete and request.url.path.startswith("/installer"):
        return attach_request_id(RedirectResponse(url="/"))

    # 检查.env文件并重定向到安装向导
    if not settings.installation_complete and \
       not request.url.path.startswith("/installer") and \
       not request.url.path.startswith("/static") and \
       not request.url.path.startswith("/api"):
        return attach_request_id(RedirectResponse(url="/installer"))

    # 访问统计：这里只统计回源动态请求（静态资源已提前返回），用于容量与恶意识别。
    # 页面浏览（PV）另由公开页内联 sendBeacon 上报，可覆盖 CDN 缓存命中的访问；
    # beacon 请求本身跳过此处统计，避免重复计入请求数。整体由标记位保护，失败不影响响应。
    traffic_tracking = False
    traffic_started = None
    is_beacon_request = request.url.path == traffic_analytics.BEACON_PATH
    if (
        settings.installation_complete
        and not is_beacon_request
        and traffic_analytics.is_enabled()
    ):
        try:
            traffic_analytics.begin_request()
            traffic_tracking = True
            traffic_started = time.perf_counter()
        except Exception:
            traffic_tracking = False

    # 公开详情页整页缓存命中：跳过设置查询、文章查询、评论装配与模板渲染。
    # 必须放在会话中间件之内，命中时才能为当前访客签发并使用自己的 CSRF 令牌。
    detail_cache_version = public_detail_cache.get_public_detail_cache_version()
    cached_detail = public_detail_cache.get_cached_public_detail_entry(
        request, version=detail_cache_version
    )
    if cached_detail is not None:
        cached_detail_html, cached_content_id = cached_detail
        # 命中缓存同样是一次真实浏览：浏览量只累加内存，不产生数据库写
        if cached_content_id > 0:
            post_views.increment_post_views(cached_content_id)
        _ensure_csrf_token(request)
        cached_response = HTMLResponse(
            content=public_detail_cache.render_cached_public_detail_html(
                cached_detail_html, request.state.csrf_token
            ),
            headers={"Cache-Control": "private, no-store"},
        )
        # 缓存命中同样是真实 HTTP 请求，必须计入请求数与并发统计
        if traffic_tracking:
            try:
                traffic_analytics.record_http_request(request, cached_response, traffic_started)
            except Exception:
                pass
            try:
                traffic_analytics.end_request()
            except Exception:
                pass
        return attach_request_id(cached_response)

    # 复用一个 request 级数据库会话给模板层（如响应式图片、相关文章过滤器）
    request_db_gen = None
    try:
        db_dependency = app.dependency_overrides.get(get_db, get_db)
        request_db_gen = db_dependency()
        request.state.db = next(request_db_gen)
    except Exception:
        request.state.db = None

    try:
        request.state.authenticated_user = auth_api._resolve_optional_authenticated_user(request, request.state.db) if request.state.db is not None else None
        # 构建全局上下文并确保 CSRF 令牌
        _populate_global_request_state(request)
        if public_list_cache.should_skip_csrf_token(request):
            # 匿名列表页不写会话：响应因此不带 Set-Cookie 与 Vary: Cookie，
            # 才能被 CDN / 反向代理整页缓存。列表页不含需要令牌的表单。
            request.state.csrf_token = ""
        else:
            _ensure_csrf_token(request)

        response = await call_next(request)
        if traffic_tracking:
            try:
                traffic_analytics.record_http_request(request, response, traffic_started)
            except Exception:
                pass
        # 列表页统一由中间件写入缓存策略：匿名 200 允许 CDN 缓存 20 秒，
        # 登录态、HTMX 分页片段与错误页一律禁止共享缓存。
        if public_list_cache.is_public_list_page_path(request.url.path):
            public_list_cache.apply_public_list_cache_headers(request, response)
        return attach_request_id(response)
    except SQLAlchemyTimeoutError:
        db_manager.record_pool_timeout()
        error_handler.logger.error(
            "数据库连接池等待超时，请求ID: %s, 路径: %s, 连接池: %s",
            request_id,
            redact_url_for_log(str(request.url), get_admin_path()),
            db_manager.get_pool_status(),
        )
        if traffic_tracking:
            try:
                traffic_analytics.record_http_request(request, None, traffic_started, forced_status=503)
            except Exception:
                pass
        return error_handler.build_database_unavailable_response(request)
    finally:
        if traffic_tracking:
            try:
                traffic_analytics.end_request()
            except Exception:
                pass
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


def _build_comment_view_context(db: Session, post_obj, request: Request) -> Dict[str, Any]:
    """构建评论区首屏上下文：批量互动摘要、隐藏内容提示、解锁状态。"""
    comments = list(getattr(post_obj, "comments", None) or [])
    comment_ids = [comment.id for comment in comments if getattr(comment, "id", None) is not None]
    visitor_token = (request.cookies.get("rewrz_visitor_token") or "").strip()

    try:
        reaction_summaries = crud_reaction.get_reaction_summaries_bulk(
            db,
            target_type="comment",
            target_ids=comment_ids,
            visitor_token=visitor_token,
        )
    except Exception:
        reaction_summaries = {}

    unlock_cookie_name = get_comment_unlock_cookie_name(getattr(post_obj, "id", 0))
    return {
        "comment_reaction_summaries": reaction_summaries,
        "comment_hide_block_count": count_hide_blocks(getattr(post_obj, "content_markdown", None)),
        "comment_unlocked": request.cookies.get(unlock_cookie_name) == "true",
    }


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
    cache_ttl_minutes: int,
    current_api_url: str,
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

        # API 地址变更后旧缓存不再对应同一图源，直接清掉避免长期占用磁盘
        if str(entry.get("api_url", "") or "").strip() != current_api_url:
            changed = True
            file_path = (cache_dir / file_name).resolve()
            if file_path.parent == cache_dir and file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
            continue

        file_path = (cache_dir / file_name).resolve()
        if file_path.parent != cache_dir:
            changed = True
            continue

        if not file_path.exists():
            changed = True
            continue

        if cache_ttl_minutes > 0:
            expire_at = _parse_utc_datetime(entry.get("expire_at"))
            if expire_at is None or expire_at <= now_utc:
                changed = True
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


def _build_cached_article_image_url(file_name: str, entry: Any) -> str:
    """生成带版本参数的本地封面 URL。

    缓存文件按 `sha256(api_url|seed)` 命名，刷新后文件名不变；只有把
    `cached_at` 作为 `?v=` 参数拼进 URL，浏览器与 CDN 才能立即拿到新图，
    同时旧 URL 可以长期强缓存而不影响后续刷新。
    """
    base_url = f"{_ARTICLE_API_CACHE_PUBLIC_PREFIX}{file_name}"
    if not isinstance(entry, dict):
        return base_url
    cached_at = _parse_utc_datetime(entry.get("cached_at"))
    if cached_at is None:
        return base_url
    return f"{base_url}?v={int(cached_at.timestamp())}"


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


def _compress_article_cache_image(payload: bytes) -> Optional[bytes]:
    """把远程封面压到列表卡片够用的尺寸，避免 4K 原图进入列表页拖慢加载与解码。"""
    try:
        with Image.open(BytesIO(payload)) as image:
            # JPEG 支持在解码阶段按目标尺寸降采样，先 draft 再解码可避开全尺寸内存峰值
            if image.format == "JPEG":
                image.draft("RGB", (_ARTICLE_API_CACHE_MAX_WIDTH, _ARTICLE_API_CACHE_MAX_WIDTH))

            # 非 JPEG 无法在解码前缩图，超出像素上限时直接放弃压缩，交给调用方回退原始字节
            if image.width * image.height > _ARTICLE_API_CACHE_MAX_PIXELS:
                return None

            image.thumbnail(
                (_ARTICLE_API_CACHE_MAX_WIDTH, _ARTICLE_API_CACHE_MAX_WIDTH),
                Image.Resampling.LANCZOS,
            )
            if image.mode != "RGB":
                image = image.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, "WEBP", quality=_ARTICLE_API_CACHE_WEBP_QUALITY, method=4)
            compressed = buffer.getvalue()
    except Exception:
        return None
    return compressed if compressed else None


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
        # 有效期为 0 时永不过期，只要文件还在就直接复用
        cache_still_valid = cache_ttl_minutes <= 0 or (
            existing_expire_at is not None and existing_expire_at > now_utc
        )
        if existing_file_name and cache_still_valid:
            existing_file_path = (cache_dir / existing_file_name).resolve()
            if existing_file_path.exists() and existing_file_path.parent == cache_dir:
                return _build_cached_article_image_url(existing_file_name, existing_entry), False

    if not download_if_missing:
        return remote_url, False

    downloaded = _download_remote_image(remote_url)
    if not downloaded:
        return remote_url, False

    image_bytes, content_type, final_url = downloaded
    compressed_bytes = _compress_article_cache_image(image_bytes)
    if compressed_bytes:
        image_bytes = compressed_bytes
        file_ext = ".webp"
    else:
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

    expire_at = now_utc + timedelta(minutes=cache_ttl_minutes) if cache_ttl_minutes > 0 else None
    cache_index[cache_key] = {
        "file_name": file_name,
        "api_url": fallback_api_url,
        "seed": seed_value,
        "cached_at": now_utc.isoformat(),
        "expire_at": expire_at.isoformat() if expire_at is not None else None,
    }
    return _build_cached_article_image_url(file_name, cache_index[cache_key]), True


def _schedule_article_api_cache_prefetch(
    *,
    seed_value: str,
    fallback_api_url: str,
    cache_ttl_minutes: int,
) -> bool:
    cache_key = _build_article_api_cache_key(fallback_api_url, seed_value)
    with _ARTICLE_API_CACHE_PREFETCH_LOCK:
        if cache_key in _ARTICLE_API_CACHE_PREFETCH_INFLIGHT:
            return False
        # 并发名额拿不到时本次直接放弃，下次访问再补缓存，避免线程与解码任务堆积
        if not _ARTICLE_API_CACHE_PREFETCH_SEMAPHORE.acquire(blocking=False):
            return False
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
            _ARTICLE_API_CACHE_PREFETCH_SEMAPHORE.release()

    thread = threading.Thread(
        target=_worker,
        name=f"article-api-cache-{cache_key[:8]}",
        daemon=True,
    )
    try:
        thread.start()
    except RuntimeError:
        # 线程创建失败时归还名额，避免预取能力被永久占用
        with _ARTICLE_API_CACHE_PREFETCH_LOCK:
            _ARTICLE_API_CACHE_PREFETCH_INFLIGHT.discard(cache_key)
        _ARTICLE_API_CACHE_PREFETCH_SEMAPHORE.release()
        return False
    return True


def _post_uses_api_fallback_cover(post: Any) -> bool:
    """判断文章是否会用到在线 API 兜底封面，已有特色图或正文图时不需要预热。"""
    if str(getattr(post, "featured_image_url", "") or "").strip():
        return False
    if "<img" in str(getattr(post, "content_html", "") or "").lower():
        return False
    return "![" not in str(getattr(post, "content_markdown", "") or "")


def _drop_article_api_cache_entries(
    cache_index: Dict[str, Dict[str, Any]],
    *,
    seeds: Set[str],
    cache_dir: Path,
) -> int:
    """按 seed 删除缓存条目与本地文件，兼容文章改 slug 后新旧两个 seed。"""
    removed = 0
    for cache_key, entry in list(cache_index.items()):
        if not isinstance(entry, dict) or str(entry.get("seed", "") or "") not in seeds:
            continue
        file_name = str(entry.get("file_name", "") or "").strip()
        if file_name:
            file_path = (cache_dir / file_name).resolve()
            if file_path.parent == cache_dir and file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
        cache_index.pop(cache_key, None)
        removed += 1
    return removed


def refresh_article_cover_cache(
    db: Session,
    post: Any,
    *,
    previous_slug: Optional[str] = None,
) -> Dict[str, Any]:
    """清理单篇文章的封面缓存并尝试重新预热，供保存文章与后台手动刷新共用。"""
    post_id = int(getattr(post, "id", 0) or 0)
    current_slug = str(getattr(post, "slug", "") or "").strip()
    result: Dict[str, Any] = {"removed": 0, "scheduled": False, "reason": ""}
    if post_id <= 0 or not current_slug:
        result["reason"] = "文章尚未生成有效标识"
        return result

    seeds = {f"{post_id}-{current_slug}"}
    old_slug = str(previous_slug or "").strip()
    if old_slug and old_slug != current_slug:
        seeds.add(f"{post_id}-{old_slug}")

    cache_dir = _ensure_article_api_cache_dir()
    cache_index = _load_article_api_cache_index(db)
    removed = _drop_article_api_cache_entries(cache_index, seeds=seeds, cache_dir=cache_dir)
    if removed:
        _upsert_runtime_setting(
            db,
            _ARTICLE_API_CACHE_INDEX_KEY,
            cache_index,
            "Article fallback API cache index",
        )
    result["removed"] = removed

    fallback_source = _normalize_article_fallback_source(
        get_page_config(db, "article_card_fallback_source", "local")
    )
    if fallback_source != "api":
        result["reason"] = "当前随机图来源不是在线 API"
        return result
    if not _parse_bool(
        get_page_config(db, "article_card_api_cache_enabled", _ARTICLE_API_CACHE_ENABLED_DEFAULT),
        _ARTICLE_API_CACHE_ENABLED_DEFAULT,
    ):
        result["reason"] = "在线 API 图片缓存未启用"
        return result
    if not _post_uses_api_fallback_cover(post):
        result["reason"] = "文章已有封面图或正文图片，无需预热"
        return result

    fallback_api_url = str(
        get_page_config(db, "article_card_fallback_api_url", _ARTICLE_FALLBACK_API_URL_DEFAULT)
        or _ARTICLE_FALLBACK_API_URL_DEFAULT
    ).strip()
    cache_ttl_minutes = _parse_bounded_int(
        get_page_config(db, "article_card_api_cache_ttl_minutes", _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT),
        _ARTICLE_API_CACHE_TTL_MINUTES_DEFAULT,
        0,
        _ARTICLE_API_CACHE_TTL_MINUTES_MAX,
    )
    result["scheduled"] = _schedule_article_api_cache_prefetch(
        seed_value=f"{post_id}-{current_slug}",
        fallback_api_url=fallback_api_url,
        cache_ttl_minutes=cache_ttl_minutes,
    )
    if not result["scheduled"]:
        result["reason"] = "已有预热任务在进行，稍后会自动完成"
    return result


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

    cache_key = str(directory)
    now = time.monotonic()
    with _ARTICLE_FALLBACK_LOCAL_CACHE_LOCK:
        cached = _ARTICLE_FALLBACK_LOCAL_CACHE.get(cache_key)
        if cached is not None and cached[0] > now:
            return list(cached[1])

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
        _ARTICLE_FALLBACK_LOCAL_CACHE[cache_key] = (
            now + _ARTICLE_FALLBACK_LOCAL_CACHE_TTL_SECONDS,
            tuple(image_urls),
        )
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

    raw_markdown = getattr(post, "content_markdown", "") or ""
    raw_html = getattr(post, "content_html", "") or ""
    public_markdown = strip_hide_blocks(raw_markdown)
    if public_markdown != raw_markdown:
        # 隐藏块内的图片不能作为公开封面
        rendered_html = get_effective_content_html(public_markdown, "")
    else:
        rendered_html = get_effective_content_html(raw_markdown, raw_html)
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


def _attach_article_cover_urls(
    db: Session,
    posts: List[Post],
    *,
    attr_name: str,
) -> None:
    """为文章列表附加统一兜底封面 URL。"""
    if not posts:
        return

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
        0,
        _ARTICLE_API_CACHE_TTL_MINUTES_MAX,
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
                cache_ttl_minutes=api_cache_ttl_minutes,
                current_api_url=fallback_api_url,
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
            # 缓存未命中时不再把第三方图片地址交给浏览器：
            # 浏览器会一直等外部接口返回，列表卡片长时间空白，load 事件也被拖住。
            # 这里先返回空，让模板走本地占位样式，同时在后台把图片抓取进本地缓存。
            return ""
        return resolved_url

    for post in posts:
        setattr(
            post,
            attr_name,
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


def _attach_post_author_profiles(db: Session, posts: List[Post], *, fallback_name: str) -> None:
    if not posts:
        return
    profile_resolver = get_public_profile_resolver()
    fallback_display_name = str(fallback_name or "博主").strip() or "博主"
    # 列表页通常同一作者，按 author_id 复用结果，避免每张卡片重复查用户表。
    profile_cache: Dict[int, Dict[str, str]] = {}

    for post in posts:
        # 只读取已加载的 author 关系，避免每篇文章触发一次懒加载查询。
        loaded_author = post.__dict__.get("author")
        author_id = (
            getattr(loaded_author, "id", None)
            if loaded_author is not None
            else getattr(post, "author_id", None)
        )
        resolved_author_id: Optional[int] = None
        if author_id is not None:
            try:
                resolved_author_id = int(author_id)
            except (TypeError, ValueError):
                resolved_author_id = None
        if resolved_author_id is not None and resolved_author_id in profile_cache:
            author_profile = profile_cache[resolved_author_id]
        else:
            author_profile = profile_resolver.resolve_author_profile(
                db,
                resolved_author_id,
                fallback_name=fallback_display_name,
            )
            if resolved_author_id is not None:
                profile_cache[resolved_author_id] = author_profile
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

public_pages_api.register_public_page_routes(
    templates=templates,
    get_page_config=get_page_config,
    resolve_homepage_posts_per_page=lambda raw_value, default_value: _resolve_posts_per_page(raw_value, default_value),
    resolve_archive_posts_per_page=lambda raw_value, default_value: _resolve_posts_per_page(
        raw_value,
        default_value,
        maximum=200,
    ),
    normalize_list_navigation_mode=_normalize_list_navigation_mode,
    build_public_pagination=_build_public_pagination,
    attach_article_cover_urls=_attach_article_cover_urls,
    attach_post_author_profiles=_attach_post_author_profiles,
    sum_post_views_metrics=_sum_post_views_metrics,
    resolve_format_by_slug=_resolve_format_by_slug,
    load_post_views_metrics_map=_load_post_views_metrics_map,
)

# 公共聚合页优先于 /{page_slug} 这类单段动态路由注册，避免静态入口被普通页面吞掉。
app.include_router(public_pages_api.router)


def _safe_local_redirect_target(raw_value: str, fallback: str = "/") -> str:
    """仅允许站内根相对路径，拒绝 //evil.com 等开放重定向。"""
    candidate = str(raw_value or "").strip()
    if not candidate:
        return fallback
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        return fallback
    if "\\" in candidate:
        return fallback

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return fallback
    return candidate


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

    safe_next_url = _safe_local_redirect_target(next_url)

    if not verify_password(password, db_post.password):
        context = build_base_template_context(request)
        context.update({
            "post": db_post,
            "next_url": safe_next_url,
            "error_message": "访问密码错误，请重试。",
        })
        return templates.TemplateResponse(request, "password_protected.html", context, status_code=403)

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
        key=get_post_access_cookie_name(post_id),
        value=build_post_access_cookie_value(post_id, db_post.password),
        httponly=True,
        samesite="lax",
        secure=should_use_secure_cookie(request),
    )
    return response


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("rewrz/static/favicon.ico")

# 兜底封面缓存单独挂载为长缓存：URL 带 ?v=<cached_at>，刷新封面后 URL 变化，
# 浏览器与 CDN 可以放心缓存一年，再次访问封面不再回源。
app.mount(
    f"/media/{_ARTICLE_API_CACHE_DIR_NAME}",
    CacheControlStaticFiles(
        directory=str(_ensure_article_api_cache_dir()),
        cache_control="public, max-age=31536000, immutable",
    ),
    name="article-api-cache",
)

# 挂载媒体上传目录
# 放在业务路由之后，确保 /media/variant/... 先命中动态缩略图路由。
app.mount(
    "/media",
    CacheControlStaticFiles(
        directory=settings.MEDIA_UPLOAD_DIR,
        cache_control="public, max-age=3600",
    ),
    name="media",
)

# 统一注册全局异常处理器（集中管理，降低重复与维护成本）
error_handler.register_error_handlers(app)

# 为CSRF保护添加会话中间件（Secure 标志按实际请求自动判定，HTTP/HTTPS/反代切换零配置）
app.add_middleware(
    RequestAwareSessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
)

# 添加设置加载中间件（在会话中间件之后）
app.add_middleware(SettingsMiddleware)

class SelectiveGZipMiddleware(GZipMiddleware):
    """只对文本类资源做 gzip。

    图片、字体、视频、压缩包本身已是二进制压缩格式，再压一遍只会白耗 CPU，
    因此这些路径/后缀直接跳过压缩。
    """

    _BINARY_SUFFIXES = (
        ".woff2", ".woff", ".ttf", ".otf", ".eot",
        ".webp", ".jpg", ".jpeg", ".png", ".gif", ".ico", ".avif", ".bmp",
        ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".wav", ".flac",
        ".zip", ".gz", ".tar", ".7z", ".rar", ".pdf", ".svgz",
    )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = str(scope.get("path") or "").lower()
            if path.startswith("/media/") or path.endswith(self._BINARY_SUFFIXES):
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


# 文本资源压缩：CSS/JS/HTML/JSON 默认完全没有压缩，
# 首屏 5 个阻塞样式表合计约 470KB，压缩后传输量可降到约 1/6
app.add_middleware(SelectiveGZipMiddleware, minimum_size=1024, compresslevel=6)

# 垃圾爬虫与扫描路径拦截必须放在最外层：命中后不建会话、不查设置、不写统计，
# 把无效请求挡在会话、模板与数据库之前。
app.add_middleware(request_guard.BotBlockMiddleware)

