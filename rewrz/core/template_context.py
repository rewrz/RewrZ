"""
模板基础上下文构建工具

提供构建模板渲染所需的通用基础上下文字段，避免在各路由中重复注入。
"""
from datetime import datetime
import re
from fastapi import Request
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..crud import category as crud_category, format as crud_format, post as crud_post
from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..core.content_intents import INTENT_SLUGS, normalize_intent_slug
from ..core.media_attachments import get_default_media_navigation
from ..core.security import decode_access_token, is_user_token_payload_valid
from ..core.url_normalizer import normalize_local_asset_url, normalize_local_asset_url_lines
from ..api import themes as themes_api

# 主页个性化设置键常量，集中管理，避免魔法字符串分散各处
HOMEPAGE_SETTING_KEYS = [
    "homepage_mode",
    "homepage_background_image_url",
    "homepage_background_video_url",
    "homepage_background_music_url",
    "homepage_music_autoplay",
]

# 基础全局设置的集中默认值（与所有页面相关且在多处使用）
DEFAULT_BASE_SETTINGS = {
    "site_title": "RewrZ",
    "tagline": "A Personal Blog System",
    "noindex_site": False,
    "block_ai_crawlers": False,
    # 新增：站点基础展示相关
    "site_logo_light": "",
    "site_logo_dark": "",
    "favicon": "",
    "site_cover_url": "",
    "admin_login_background_image_url": "",
    "admin_login_background_video_url": "",
    "public_contact_email": "",
    # 新增：社交与页脚相关
    "social_links": [],  # [{ icon: str, url: str }, ...]
    "custom_footer_text": "",
    "icp_beian": "",
    "gongan_beian": "",
    "rss_enabled": True,
    "copyright_info": "",
    "list_navigation_mode": "pagination",
    "code_highlight_theme": "github-dark",
}

# highlight.js 可选主题（需与本地样式文件名一致）
CODE_HIGHLIGHT_THEME_OPTIONS = (
    "github-dark",
    "github-light",
    "nord",
)

# 主页个性化设置的集中默认值，供全局读取与回退使用
DEFAULT_HOMEPAGE_SETTINGS = {
    "homepage_mode": "default",
    "homepage_background_image_url": "",
    "homepage_background_video_url": "",
    "homepage_background_music_url": "",
    "homepage_music_autoplay": False,
}


def _render_copyright_info(raw_value: str, current_year: int) -> str:
    """规范化页脚版权文案，确保动态年份始终存在。"""
    text = str(raw_value or "").strip()
    if not text:
        return ""
    if "{year}" in text:
        return text.replace("{year}", str(current_year))
    if re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", text):
        return text
    if "&copy;" in text:
        return text.replace("&copy;", f"&copy; {current_year}", 1)
    if "©" in text:
        return text.replace("©", f"© {current_year}", 1)
    return f"&copy; {current_year} {text}"


def build_base_template_context(request: Request) -> dict:
    """
    构建模板基础上下文字典，包含所有页面共享的全局字段
    
    现在使用中间件提供的统一设置数据，同时保持向后兼容性
    """
    # 优先复用 request.state.db，避免重复创建会话
    db: Session = getattr(request.state, "db", None)
    db_gen = None
    if db is None:
        db_gen = get_db()
        db = next(db_gen)
    
    token = str((request.cookies.get("access_token") or "")).strip()
    is_logged_in = False
    theme_persist_allowed = False
    if token:
        payload = decode_access_token(token)
        if payload:
            raw_user_id = payload.get("sub")
            try:
                user_id = int(raw_user_id)
            except (TypeError, ValueError):
                user_id = 0
            if user_id > 0:
                current_user = crud_user.get_user(db, user_id=user_id)
                is_logged_in = is_user_token_payload_valid(current_user, payload)
                if is_logged_in and current_user is not None:
                    user_role = str(getattr(current_user, "role", "") or "").strip().lower()
                    theme_persist_allowed = user_role in {"admin", "super_admin"}

    # 仅保留三种内容类型，避免旧格式继续出现在导航中
    all_formats = crud_format.get_formats(db)
    intent_order = {slug: index for index, slug in enumerate(INTENT_SLUGS)}
    post_formats = [
        fmt for fmt in all_formats
        if normalize_intent_slug(getattr(fmt, "slug", None)) in INTENT_SLUGS
    ]
    post_formats.sort(
        key=lambda fmt: intent_order.get(normalize_intent_slug(getattr(fmt, "slug", None)) or "", 999)
    )

    categories = crud_category.get_categories(db)
    nav_categories = []
    for category in categories:
        published_posts = [
            post for post in list(getattr(category, "posts", []) or [])
            if str(getattr(post, "status", "") or "").strip().lower() == "published"
            and str(getattr(post, "post_type", "") or "").strip().lower() == "post"
        ]
        if not published_posts:
            continue
        setattr(category, "posts_count", len(published_posts))
        nav_categories.append(category)

    # 获取所有已发布的自定义页面
    custom_pages = crud_post.get_posts(db, post_type="page", status="published")
    
    # 获取中间件提供的统一设置数据
    settings = getattr(request.state, "settings", {})
    custom_themes_setting = crud_setting.get_setting(db, key="custom_themes")
    custom_themes = custom_themes_setting.value.get("value") if custom_themes_setting else {}
    current_theme = themes_api.resolve_theme_name(
        getattr(request.state, "current_theme", None),
        custom_themes,
    )
    current_atmosphere = themes_api.normalize_atmosphere_name(getattr(request.state, "current_atmosphere", None))
    background_settings = getattr(request.state, "background_image_settings", {"type": "none", "custom_url": None}) or {"type": "none", "custom_url": None}
    glass_intensity = themes_api.normalize_glass_intensity(getattr(request.state, "glass_intensity", "medium"))
    
    # 构建上下文，优先使用结构化的设置数据，回退到平铺字段（向后兼容）
    current_year = datetime.now().year
    raw_copyright_info = settings.get("site", {}).get("copyright_info") or getattr(request.state, "copyright_info", DEFAULT_BASE_SETTINGS["copyright_info"])
    rendered_copyright_info = _render_copyright_info(raw_copyright_info, current_year)

    context = {
        "request": request,  # 添加 request 对象到上下文
        "settings": settings,  # 新增：结构化的设置对象
        
        # 保持向后兼容性：继续提供平铺的字段
        "atmosphere_class": getattr(request.state, "atmosphere_class", ""),
        "current_theme": current_theme,
        "current_atmosphere": current_atmosphere,
        "glass_intensity": glass_intensity,
        "background_image_settings": background_settings,
        "theme_csrf_token": getattr(request.state, "csrf_token", ""),
        "theme_persist_allowed": theme_persist_allowed,
        "site_title": settings.get("site", {}).get("title") or getattr(request.state, "site_title", DEFAULT_BASE_SETTINGS["site_title"]),
        "tagline": settings.get("site", {}).get("tagline") or getattr(request.state, "tagline", DEFAULT_BASE_SETTINGS["tagline"]),
        "noindex_site": settings.get("seo", {}).get("noindex_site") if settings.get("seo", {}).get("noindex_site") is not None else getattr(request.state, "noindex_site", DEFAULT_BASE_SETTINGS["noindex_site"]),
        "block_ai_crawlers": settings.get("seo", {}).get("block_ai_crawlers") if settings.get("seo", {}).get("block_ai_crawlers") is not None else getattr(request.state, "block_ai_crawlers", DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
        
        # 站点展示相关（logo / favicon）
        "site_logo_light": normalize_local_asset_url(settings.get("site", {}).get("logo_light") or getattr(request.state, "site_logo_light", DEFAULT_BASE_SETTINGS["site_logo_light"])),
        "site_logo_dark": normalize_local_asset_url(settings.get("site", {}).get("logo_dark") or getattr(request.state, "site_logo_dark", DEFAULT_BASE_SETTINGS["site_logo_dark"])),
        "favicon": normalize_local_asset_url(settings.get("site", {}).get("favicon") or getattr(request.state, "favicon", DEFAULT_BASE_SETTINGS["favicon"])),
        "site_cover_url": normalize_local_asset_url(settings.get("site", {}).get("cover_url") or getattr(request.state, "site_cover_url", DEFAULT_BASE_SETTINGS["site_cover_url"])),
        "admin_login_background_image_url": normalize_local_asset_url(settings.get("site", {}).get("admin_login_background_image_url") or getattr(request.state, "admin_login_background_image_url", DEFAULT_BASE_SETTINGS["admin_login_background_image_url"])),
        "admin_login_background_video_url": normalize_local_asset_url(settings.get("site", {}).get("admin_login_background_video_url") or getattr(request.state, "admin_login_background_video_url", DEFAULT_BASE_SETTINGS["admin_login_background_video_url"])),
        "public_contact_email": settings.get("site", {}).get("public_contact_email") or getattr(request.state, "public_contact_email", DEFAULT_BASE_SETTINGS["public_contact_email"]),
        
        # 社交与页脚相关
        "social_links": getattr(request.state, "social_links", DEFAULT_BASE_SETTINGS["social_links"]),
        "custom_footer_text": settings.get("site", {}).get("custom_footer_text") or getattr(request.state, "custom_footer_text", DEFAULT_BASE_SETTINGS["custom_footer_text"]),
        "icp_beian": settings.get("site", {}).get("icp_beian") or getattr(request.state, "icp_beian", DEFAULT_BASE_SETTINGS["icp_beian"]),
        "gongan_beian": settings.get("site", {}).get("gongan_beian") or getattr(request.state, "gongan_beian", DEFAULT_BASE_SETTINGS["gongan_beian"]),
        "rss_enabled": settings.get("rss", {}).get("enabled") if settings.get("rss", {}).get("enabled") is not None else getattr(request.state, "rss_enabled", DEFAULT_BASE_SETTINGS["rss_enabled"]),
        "copyright_info": raw_copyright_info,
        "copyright_info_rendered": rendered_copyright_info,
        "current_year": current_year,
        # 主页个性化设置（为模板提供平铺字段，兼容旧模板访问方式）
        "homepage_mode": settings.get("homepage", {}).get("mode") or getattr(request.state, "homepage_mode", DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]),
        "homepage_background_image_url": normalize_local_asset_url_lines(
            settings.get("homepage", {}).get("background_image_url")
            or getattr(request.state, "homepage_background_image_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_image_url"])
        ),
        "homepage_background_video_url": settings.get("homepage", {}).get("background_video_url") or getattr(request.state, "homepage_background_video_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_video_url"]),
        "homepage_background_music_url": settings.get("homepage", {}).get("background_music_url") or getattr(request.state, "homepage_background_music_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_music_url"]),
        "homepage_music_autoplay": settings.get("homepage", {}).get("music_autoplay") if settings.get("homepage", {}).get("music_autoplay") is not None else getattr(request.state, "homepage_music_autoplay", DEFAULT_HOMEPAGE_SETTINGS["homepage_music_autoplay"]),
        # 分页配置（供归档/相关文章等模板使用）
        "homepage_posts_limit": settings.get("pagination", {}).get("homepage_posts_limit") if settings.get("pagination", {}).get("homepage_posts_limit") is not None else getattr(request.state, "homepage_posts_limit", 10),
        "archive_posts_limit": settings.get("pagination", {}).get("archive_posts_limit") if settings.get("pagination", {}).get("archive_posts_limit") is not None else getattr(request.state, "archive_posts_limit", 20),
        "search_results_limit": settings.get("pagination", {}).get("search_results_limit") if settings.get("pagination", {}).get("search_results_limit") is not None else getattr(request.state, "search_results_limit", 15),
        "related_posts_limit": settings.get("pagination", {}).get("related_posts_limit") if settings.get("pagination", {}).get("related_posts_limit") is not None else getattr(request.state, "related_posts_limit", 5),
        "list_navigation_mode": settings.get("pagination", {}).get("list_navigation_mode") or getattr(request.state, "list_navigation_mode", "pagination"),
        "code_highlight_theme": settings.get("display", {}).get("code_highlight_theme") or getattr(request.state, "code_highlight_theme", DEFAULT_BASE_SETTINGS["code_highlight_theme"]),
        
        # 动态导航菜单数据
        "categories": nav_categories,
        "post_formats": post_formats,
        "media_nav_items": get_default_media_navigation(),
        "custom_pages": custom_pages,
        "is_logged_in": is_logged_in,
    }
    
    if db_gen is not None:
        try:
            db_gen.close()
        except Exception:
            pass

    return context

