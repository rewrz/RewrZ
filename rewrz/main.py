"""
RewrZ 博客系统主应用模块

基于FastAPI构建的个人博客系统，支持多重身份内容系统、动态主题、
反垃圾评论、版本快照等功能。采用HTMX + Tailwind CSS前端技术栈。
"""
import os
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from .core.template_filters import get_templates  # 导入带过滤器的模板系统
from .core.template_context import build_base_template_context
from .core.database import get_db, create_all_tables
from .core.config import settings  # 导入settings实例
from .schemas import UserCreate, User, PostCreate, PostUpdate
from .crud import user as crud_user
from .core.security import get_current_user  # 导入get_current_user函数
from .api import auth as auth_api
from .api import installer as installer_api
from .api import posts as posts_api
from .api import media as media_api # Import the media router
from .api import comments as comments_api # Import the comments router
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
from .api import error_config as error_config_api # 导入错误处理配置路由
from .api import admin_dashboard as admin_dashboard_api # 导入仪表盘API路由
from .api import categories as categories_api # 导入分类API路由
from .api import tags as tags_api # 导入标签API路由
from .api import captcha as captcha_api # 导入验证码API路由
from .core.avatar import get_avatar_service
from .crud import post as crud_post
from .crud import category as crud_category
from .crud import tag as crud_tag
from .crud import setting as crud_setting # Import crud_setting
from .crud import format as crud_format # 导入格式CRUD模块以修复未定义变量错误
from .core import error_handler  # 导入错误处理模块
from typing import List, Optional
from datetime import date, datetime # 导入date和datetime用于纪念日检查和主题调度
from starlette.middleware.sessions import SessionMiddleware # 导入会话中间件
from .core.security import generate_csrf_token # 导入CSRF令牌生成函数

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
    title="RewrZ Blog System",
    description="A Personal Blog System built with FastAPI, supporting multi-identity content system, dynamic themes, anti-spam comments, version snapshots, and more. Featuring HTMX + Tailwind CSS frontend stack.",
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
    async def dynamic_admin_login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
        """
        动态后台登录端点
        这是真正的安全登录入口，路径随 ADMIN_PATH 动态变化
        """
        return await auth_api.login_for_access_token_impl(response, form_data, db)
    
    # 注册后台仪表盘
    @app.get(f"{admin_path}/dashboard", response_class=HTMLResponse)
    async def dynamic_admin_dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
        return templates.TemplateResponse("admin/dashboard.html", {"request": request, "user": current_user, "admin_path": admin_path})
    
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
        site_url: str = Form(...),
        admin_email: str = Form(...),
        site_logo_light: Optional[str] = Form(None),
        site_logo_dark: Optional[str] = Form(None),
        favicon: Optional[str] = Form(None),
        copyright_info: str = Form(...),
        custom_footer_text: Optional[str] = Form(None),
        icp_beian: Optional[str] = Form(None),
        gongan_beian: Optional[str] = Form(None),
        social_links_json: str = Form("[]"),
        anniversaries_json: str = Form("[]"),
        sitemap_enabled: bool = Form(False),
        noindex_site: bool = Form(False),
        block_ai_crawlers: bool = Form(False),
        rss_enabled: bool = Form(False),
        rss_items_limit: int = Form(20),
        rss_cache_duration: int = Form(60),
        rss_description: Optional[str] = Form(None),
        homepage_posts_limit: int = Form(10),
        archive_posts_limit: int = Form(20),
        search_results_limit: int = Form(15),
        related_posts_limit: int = Form(5), # 打赏功能相关参数之前的参数
        # 打赏功能相关参数
        donation_enabled: bool = Form(False),
        donation_title: str = Form('如果这篇文章对您有帮助，请考虑支持作者'),
        donation_description: str = Form('您的支持是我创作的动力！'),
        donation_qr_code_url: Optional[str] = Form(None),
        donation_link_text: Optional[str] = Form(None),
        donation_link_url: Optional[str] = Form(None),
        donation_style_theme: str = Form('elegant'),
        donation_show_position: str = Form('article_end'),
        csrf_token: str = Form(...),
    ):
        return await settings_api.update_admin_settings(
            request, db, current_user, site_title, tagline, site_url, admin_email,
            site_logo_light, site_logo_dark, favicon, copyright_info, custom_footer_text,
            icp_beian, gongan_beian, social_links_json, anniversaries_json, sitemap_enabled,
            noindex_site, block_ai_crawlers, rss_enabled, rss_items_limit, rss_cache_duration,
            rss_description, homepage_posts_limit, archive_posts_limit, search_results_limit,
            related_posts_limit,
            # 打赏功能相关参数
            donation_enabled, donation_title, donation_description,
            donation_qr_code_url, donation_link_text, donation_link_url,
            donation_style_theme, donation_show_position,
            csrf_token
        )
    
    # 注册后台路径更新API端点
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
        return await themes_api.update_theme(request, db, current_user)
    
    @app.post(f"{admin_path}/themes/custom")
    async def dynamic_create_custom_theme(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await themes_api.create_custom_theme(request, db, current_user)
    
    @app.delete(f"{admin_path}/themes/custom/{{theme_name}}")
    async def dynamic_delete_custom_theme(theme_name: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await themes_api.delete_custom_theme(theme_name, request, db, current_user)
    
    @app.post(f"{admin_path}/themes/schedule")
    async def dynamic_schedule_themes(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await themes_api.schedule_themes(request, db, current_user)
    
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
        db: Session = Depends(get_db), 
        current_user: User = Depends(get_current_user)
    ):
        from .crud import post as crud_post
        
        # 使用已有的 get_posts 函数来获取文章列表，确保按发布时间降序排列
        posts = crud_post.get_posts(db, post_type="post", limit=50, status=status)
        
        # 如果有搜索条件，需要额外过滤
        if search:
            posts = [post for post in posts if search.lower() in post.title.lower() or search.lower() in post.content_markdown.lower()]
        
        # 如果有分类筛选，需要额外过滤
        if category:
            try:
                category_id = int(category)
                posts = [post for post in posts if any(cat.id == category_id for cat in post.categories)]
            except ValueError:
                # 如果 category 不是有效的整数，则忽略筛选条件
                pass
        
        # 获取所有分类用于筛选
        categories = crud_category.get_categories(db)
        
        return templates.TemplateResponse("admin/posts_list.html", {
            "request": request, 
            "posts": posts, 
            "categories": categories,
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册获取分类选项的API端点
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
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        allow_comments: bool = Form(True),
        category_ids: Optional[List[int]] = Form(None),
        tags: Optional[str] = Form(None),
        format_ids: Optional[List[int]] = Form(None),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.create_post_api(request, title, content, slug, excerpt, featured_image_url, status,allow_comments, category_ids, tags, format_ids, license_type, csrf_token, db, current_user)
    
    @app.post(f"{admin_path}/posts/{{post_id}}")
    async def dynamic_update_post(
        post_id: int,
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        allow_comments: bool = Form(True),
        category_ids: Optional[List[int]] = Form(None),
        tags: Optional[str] = Form(None),
        format_ids: Optional[List[int]] = Form(None),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.update_post_api(request, post_id, title, content, slug, excerpt, featured_image_url, status, allow_comments, category_ids, tags, format_ids, license_type, csrf_token, db, current_user)
    
    # 注册后台分类管理页面
    @app.get(f"{admin_path}/categories", response_class=HTMLResponse)
    async def dynamic_admin_categories_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .crud import category as crud_category
        categories = crud_category.get_categories(db)
        return templates.TemplateResponse("admin/categories_list.html", {
            "request": request, 
            "categories": categories, 
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册后台标签管理页面
    @app.get(f"{admin_path}/tags", response_class=HTMLResponse)
    async def dynamic_admin_tags_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .crud import tag as crud_tag
        tags = crud_tag.get_tags(db)
        return templates.TemplateResponse("admin/tags_list.html", {
            "request": request, 
            "tags": tags, 
            "user": current_user,
            "admin_path": admin_path
        })
    
    # 注册后台评论管理页面
    @app.get(f"{admin_path}/comments", response_class=HTMLResponse)
    async def dynamic_admin_comments_page(
        request: Request, 
        status: Optional[str] = None,
        db: Session = Depends(get_db), 
        current_user: User = Depends(get_current_user)
    ):
        from .crud import comment as crud_comment
        comments = crud_comment.get_comments(db, limit=50, sort_by_latest=True, status=status)
        
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

        return templates.TemplateResponse("admin/comments_list.html", {
            "request": request, 
            "comments_with_avatars": comments_with_avatars, 
            "user": current_user,
            "admin_path": admin_path,
            "current_status": status
        })
    
    # 注册后台页面管理页面
    @app.get(f"{admin_path}/pages", response_class=HTMLResponse)
    async def dynamic_admin_pages_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .crud import post as crud_post
        # 获取类型为页面的文章，按发布时间降序排列
        pages = crud_post.get_posts(db, post_type="page", limit=50)
        return templates.TemplateResponse("admin/pages_list.html", {
            "request": request, 
            "pages": pages, 
            "user": current_user,
            "admin_path": admin_path
        })
    
    @app.post(f"{admin_path}/pages/new")
    async def dynamic_create_page(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        allow_comments: bool = Form(True),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.create_page_api(request, title, content, slug, excerpt, featured_image_url, status, allow_comments, license_type, csrf_token, db, current_user)
    
    @app.post(f"{admin_path}/pages/{{page_id}}")
    async def dynamic_update_page(
        page_id: int,
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        slug: Optional[str] = Form(None),
        excerpt: Optional[str] = Form(None),
        featured_image_url: Optional[str] = Form(None),
        status: str = Form("draft"),
        allow_comments: bool = Form(True),
        license_type: str = Form("cc_by_nc_sa_4"),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        return await posts_api.update_page_api(request, page_id, title, content, slug, excerpt, featured_image_url, status, allow_comments, license_type, csrf_token, db, current_user)
    
    # 注册后台系统信息页面
    @app.get(f"{admin_path}/system-info", response_class=HTMLResponse)
    async def dynamic_admin_system_info_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .api import system_info as system_info_api
        return await system_info_api.system_info_page(request, db, current_user)
    
    @app.get(f"{admin_path}/api/system-info")
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

    # 注册数据管理页面
    @app.get(f"{admin_path}/data-management", response_class=HTMLResponse)
    async def dynamic_admin_data_management_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        return await data_api.data_management_page(request, db, current_user)

    # 包含数据导入导出路由
    app.include_router(data_api.router, prefix=admin_path)
    
    # 注册数据统计API
    @app.get(f"{admin_path}/api/dashboard/stats")
    async def dynamic_get_dashboard_stats(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        from .api import admin_dashboard as admin_dashboard_api
        return await admin_dashboard_api.get_dashboard_stats(request, db)

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
        enable_error_caching: bool = Form(True),
        error_cache_duration: int = Form(3600),
        enable_error_logging: bool = Form(True),
        log_level: str = Form("INFO"),
        enable_performance_optimization: bool = Form(True),
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
    
    # 动态注册分类API路由
    app.include_router(categories_api.router, prefix=admin_path)
    
    # 动态注册标签API路由
    app.include_router(tags_api.router, prefix=admin_path)

# 包含安装向导路由
app.include_router(installer_api.router)
# 包含文章路由
app.include_router(posts_api.router)
# 包含媒体路由
app.include_router(media_api.router)
# 包含评论路由
app.include_router(comments_api.router)
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

# 抽取：构建全局请求上下文（初始化默认值、读取设置、主题调度/纪念日、后台路径）
def _populate_global_request_state(request: Request) -> None:
    # 初始化全局上下文变量
    request.state.atmosphere_class = ""
    request.state.site_title = "RewrZ"
    request.state.tagline = "A Personal Blog System"
    request.state.noindex_site = False
    request.state.block_ai_crawlers = False
    request.state.admin_path = get_admin_path()  # 添加后台路径
    request.state.csrf_token = ""  # 初始化CSRF令牌
    # 初始化主页个性化设置
    request.state.homepage_mode = "default"
    request.state.homepage_background_image_url = ""
    request.state.homepage_background_video_url = ""
    request.state.homepage_background_music_url = ""
    request.state.homepage_music_autoplay = False

    db = next(get_db())
    try:
        # 获取并设置所有全局上下文
        settings_keys = {
            "site_title": "RewrZ",
            "tagline": "A Personal Blog System",
            "noindex_site": False,
            "block_ai_crawlers": False,
            # 主页个性化设置
            "homepage_mode": "default",
            "homepage_background_image_url": "",
            "homepage_background_video_url": "",
            "homepage_background_music_url": "",
            "homepage_music_autoplay": False,
        }
        all_settings = crud_setting.get_settings_by_keys(db, list(settings_keys.keys()))
        for key, default_value in settings_keys.items():
            setattr(request.state, key, all_settings.get(key, default_value))

        # 检查主题调度和氛围主题
        # 检查是否有计划中的氛围主题
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
                            scheduled_atmosphere = item.get("atmosphere")
                            break
                    except (ValueError, KeyError):
                        continue
        
        if scheduled_atmosphere:
            request.state.atmosphere_class = f"atmosphere-{scheduled_atmosphere}"
        
        else:
            # 仅在没有计划主题时检查纪念日
            anniversaries_setting = crud_setting.get_setting(db, key="anniversaries")
            if anniversaries_setting and anniversaries_setting.value:
                anniversaries = anniversaries_setting.value.get("value", [])
                today = date.today()
                for anniversary in anniversaries:
                    if isinstance(anniversary, dict) and "month" in anniversary and "day" in anniversary and "type" in anniversary:
                        try:
                            if anniversary["month"] == today.month and anniversary["day"] == today.day:
                                request.state.atmosphere_class = f"atmosphere-{anniversary['type'].lower()}"
                                break
                        except (KeyError, TypeError):
                            continue
    finally:
        db.close() # 关闭会话

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

    # 检查.env文件并重定向到安装向导
    if not settings.installation_complete and \
       not request.url.path.startswith("/installer") and \
       not request.url.path.startswith("/static") and \
       not request.url.path.startswith("/api"):
        return RedirectResponse(url="/installer")

    # 构建全局上下文并确保 CSRF 令牌
    _populate_global_request_state(request)
    _ensure_csrf_token(request)

    response = await call_next(request)
    return response

def get_page_config(db: Session, config_key: str, default_value: int) -> int:
    """
    获取页面显示配置
    
    Args:
        db: 数据库会话
        config_key: 配置键名
        default_value: 默认值
    
    Returns:
        配置的数值
    """
    setting = crud_setting.get_setting(db, key=config_key)
    return setting.value.get("value") if setting and setting.value else default_value

def get_admin_path() -> str:
    """
    获取后台路径配置
    
    Returns:
        后台路径
    """
    return settings.ADMIN_PATH.rstrip('/')

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("rewrz/static/favicon.ico")


def _load_homepage_settings_for_template(db: Session, request: Request) -> dict:
    homepage_setting_keys = [
        "homepage_mode",
        "homepage_background_image_url",
        "homepage_background_video_url",
        "homepage_background_music_url",
        "homepage_music_autoplay",
    ]
    homepage_settings = crud_setting.get_settings_by_keys(db, homepage_setting_keys)
    settings_dict = {}
    for key in homepage_setting_keys:
        setting_obj = homepage_settings.get(key)
        if setting_obj and getattr(setting_obj, 'value', None) and 'value' in setting_obj.value:
            settings_dict[key] = setting_obj.value['value']
        else:
            # 回退到 request.state 中的默认值（已由 _populate_global_request_state 设置）
            settings_dict[key] = getattr(request.state, key, "")
    return settings_dict

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db: Session = Depends(get_db)):
    """
    首页路由
    
    显示最新的文章，数量根据后台配置确定，支持多重身份内容系统的格式优先级渲染，包含动态SEO元数据
    """
    # 获取首页文章数量配置
    homepage_posts_limit = get_page_config(db, "homepage_posts_limit", 10)
    # 获取已发布的文章，数量根据后台配置确定
    posts = crud_post.get_posts(db, skip=0, limit=homepage_posts_limit, status="published")
    
    # 获取首页SEO元数据
    from .api.seo import _generate_homepage_seo_data
    seo_data = _generate_homepage_seo_data(request, db)
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "posts": posts, 
        "seo_data": seo_data,
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

@app.get("/posts/{post_slug}", response_class=HTMLResponse)
async def read_post(request: Request, post_slug: str, db: Session = Depends(get_db)):
    """
    文章详情页路由
    
    根据文章别名显示单篇文章的详细内容，包含动态SEO元数据
    """
    db_post = crud_post.get_post_by_slug(db, slug=post_slug)
    if db_post is None or db_post.status != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 获取SEO元数据
    from .api.seo import _generate_post_seo_data
    seo_data = _generate_post_seo_data(db_post, request, db)
    
    # 获取打赏配置
    from .core.donation_system import get_donation_system
    donation_system = get_donation_system(db)
    donation_config = donation_system.settings
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("post_detail.html", {
        "request": request,
        "post": db_post,
        "seo_data": seo_data,
        "donation_config": donation_config,
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

@app.get("/archives/by-category/{category_slug}", response_class=HTMLResponse)
async def posts_by_category(request: Request, category_slug: str, db: Session = Depends(get_db)):
    """
    按分类归档页面
    
    显示指定分类下的所有文章
    """
    category = crud_category.get_category_by_slug(db, slug=category_slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    posts = crud_post.get_posts_by_category(db, category_id=category.id)
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("category_archive.html", {
        "request": request, 
        "category": category, 
        "posts": posts, 
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

@app.get("/archives/by-tag/{tag_slug}", response_class=HTMLResponse)
async def posts_by_tag(request: Request, tag_slug: str, db: Session = Depends(get_db)):
    """
    按标签归档页面
    
    显示指定标签下的所有文章
    """
    tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    posts = crud_post.get_posts_by_tag(db, tag_id=tag.id)
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("tag_archive.html", {
        "request": request, 
        "tag": tag, 
        "posts": posts, 
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

# 占位符路由：/archives/2025/08/
@app.get("/archives/{year}/{month}", response_class=HTMLResponse)
async def posts_by_month(request: Request, year: int, month: int, db: Session = Depends(get_db)):
    """
    按年月归档页面
    
    显示指定年月的所有文章
    """
    # 这需要更复杂的CRUD函数来按年/月过滤
    archive_posts_limit = get_page_config(db, "archive_posts_limit", 20)
    posts = crud_post.get_posts(db, skip=0, limit=archive_posts_limit) # 使用配置的文章数量
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("monthly_archive.html", {
        "request": request, 
        "year": year, 
        "month": month, 
        "posts": posts, 
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

# 占位符路由：/archives
@app.get("/archives", response_class=HTMLResponse)
async def archives_page(request: Request, db: Session = Depends(get_db)):
    """
    总归档页面
    
    显示所有文章的归档列表
    """
    archive_posts_limit = get_page_config(db, "archive_posts_limit", 20)
    posts = crud_post.get_posts(db, skip=0, limit=archive_posts_limit) # 使用配置的文章数量
    
    # 准备主页个性化设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("archives.html", {
        "request": request, 
        "posts": posts, 
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

# 聚合页面路由：/formats/photos, /formats/weibo, /formats/video, /formats/music
@app.get("/formats/{format_slug}", response_class=HTMLResponse)
async def format_page(request: Request, format_slug: str, db: Session = Depends(get_db)):
    """
    格式归档页面（多重身份内容系统）
    
    根据格式别名显示指定格式的所有文章，URL符合 /formats/{format_slug} 规范
    """
    format = crud_format.get_format_by_slug(db, slug=format_slug)
    if format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    posts = crud_post.get_posts_by_format(db, format_id=format.id)
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("format_archive.html", {
        "request": request, 
        "format": format, 
        "format_slug": format_slug,  # 将format_slug传递给模板
        "posts": posts, 
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

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
    
    # 检查是否存在具有该别名的页面
    db_page = crud_post.get_post_by_slug(db, slug=page_slug)
    if db_page is None or db_page.post_type != "page" or (db_page.status != "published" and not hasattr(request.state, 'user')):
        # 如果没有找到页面，检查是否是其他特殊路由
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 获取SEO元数据
    from .api.seo import _generate_post_seo_data
    seo_data = _generate_post_seo_data(db_page, request, db)
    
    # 准备设置上下文 (包含主页个性化设置)
    settings_dict = _load_homepage_settings_for_template(db, request)
    
    return templates.TemplateResponse("page.html", {
        "request": request, 
        "post": db_page,
        "seo_data": seo_data,
        **build_base_template_context(request),
        "settings": settings_dict,  # 传递设置字典给模板
    })

# 统一注册全局异常处理器（集中管理，降低重复与维护成本）
error_handler.register_error_handlers(app)

# 为CSRF保护添加会话中间件
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
