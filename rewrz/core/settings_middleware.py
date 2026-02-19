"""
设置加载中间件

在每个请求开始时统一加载所有设置数据到 request.state，
避免在各个路由中重复查询数据库，提高性能并统一数据流。
"""
from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from typing import Dict, Any

from ..crud import setting as crud_setting
from ..core.database import get_db
from ..core.template_context import (
    HOMEPAGE_SETTING_KEYS, 
    DEFAULT_HOMEPAGE_SETTINGS, 
    DEFAULT_BASE_SETTINGS
)


class SettingsMiddleware(BaseHTTPMiddleware):
    """
    设置加载中间件
    
    在每个请求处理前，从数据库加载所有设置并存储到 request.state 中，
    提供统一的设置访问接口。
    """
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        中间件主要逻辑：加载设置数据到 request.state
        """
        db_gen = None
        try:
            # 优先复用 request 级数据库会话
            db: Session = getattr(request.state, "db", None)
            if db is None:
                db_gen = get_db()
                db = next(db_gen)

            if db is None:
                raise RuntimeError("Database session is unavailable")
            
            # 定义需要加载的所有设置键
            all_setting_keys = [
                # 基础站点设置
                "site_title", "tagline", "site_url", "admin_email",
                "public_contact_email",
                "site_logo_light", "site_logo_dark", "favicon",
                "site_cover_url",
                "copyright_info", "custom_footer_text", "icp_beian", "gongan_beian",
                
                # SEO设置
                "noindex_site", "block_ai_crawlers",
                
                # 社交和其他设置
                "social_links_json", "anniversaries_json",
                
                # RSS设置
                "rss_enabled", "rss_items_limit", "rss_cache_duration", "rss_description",
                
                # 站点地图设置
                "sitemap_enabled",
                
                # 分页设置
                "homepage_posts_limit", "archive_posts_limit", "search_results_limit", "related_posts_limit", "list_navigation_mode",
                # /formats/article 图文卡片兜底图设置
                "article_card_fallback_source", "article_card_fallback_api_url", "article_card_fallback_local_dir",
                
                # 打赏功能设置
                "donation_enabled", "donation_title", "donation_description",
                "donation_qr_code_url", "donation_link_text", "donation_link_url",
                "donation_style_theme", "donation_show_position",
            ]
            
            # 添加主页个性化设置键
            all_setting_keys.extend(HOMEPAGE_SETTING_KEYS)
            
            # 批量加载所有设置
            all_settings = crud_setting.get_settings_by_keys(db, all_setting_keys)
            
            # 创建结构化的设置对象
            settings_dict = {
                "site": {
                    "title": all_settings.get("site_title", DEFAULT_BASE_SETTINGS["site_title"]),
                    "tagline": all_settings.get("tagline", DEFAULT_BASE_SETTINGS["tagline"]),
                    "url": all_settings.get("site_url", ""),
                    "admin_email": all_settings.get("admin_email", ""),
                    "public_contact_email": all_settings.get("public_contact_email", ""),
                    "logo_light": all_settings.get("site_logo_light", DEFAULT_BASE_SETTINGS["site_logo_light"]),
                    "logo_dark": all_settings.get("site_logo_dark", DEFAULT_BASE_SETTINGS["site_logo_dark"]),
                    "favicon": all_settings.get("favicon", DEFAULT_BASE_SETTINGS["favicon"]),
                    "cover_url": all_settings.get("site_cover_url", DEFAULT_BASE_SETTINGS["site_cover_url"]),
                    "copyright_info": all_settings.get("copyright_info", DEFAULT_BASE_SETTINGS["copyright_info"]),
                    "custom_footer_text": all_settings.get("custom_footer_text", DEFAULT_BASE_SETTINGS["custom_footer_text"]),
                    "icp_beian": all_settings.get("icp_beian", DEFAULT_BASE_SETTINGS["icp_beian"]),
                    "gongan_beian": all_settings.get("gongan_beian", DEFAULT_BASE_SETTINGS["gongan_beian"]),
                },
                "seo": {
                    "noindex_site": all_settings.get("noindex_site", DEFAULT_BASE_SETTINGS["noindex_site"]),
                    "block_ai_crawlers": all_settings.get("block_ai_crawlers", DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
                },
                "social": {
                    "links_json": all_settings.get("social_links_json", "[]"),
                    "anniversaries_json": all_settings.get("anniversaries_json", "[]"),
                },
                "rss": {
                    "enabled": all_settings.get("rss_enabled", DEFAULT_BASE_SETTINGS["rss_enabled"]),
                    "items_limit": all_settings.get("rss_items_limit", 20),
                    "cache_duration": all_settings.get("rss_cache_duration", 60),
                    "description": all_settings.get("rss_description", ""),
                },
                "pagination": {
                    "homepage_posts_limit": all_settings.get("homepage_posts_limit", 10),
                    "archive_posts_limit": all_settings.get("archive_posts_limit", 20),
                    "search_results_limit": all_settings.get("search_results_limit", 15),
                    "related_posts_limit": all_settings.get("related_posts_limit", 5),
                    "list_navigation_mode": all_settings.get("list_navigation_mode", "pagination"),
                },
                "article_cards": {
                    "fallback_source": all_settings.get("article_card_fallback_source", "local"),
                    "fallback_api_url": all_settings.get(
                        "article_card_fallback_api_url",
                        "https://www.loliapi.com/acg/",
                    ),
                    "fallback_local_dir": all_settings.get("article_card_fallback_local_dir", "rewrz/static/images/anime/random"),
                },
                "donation": {
                    "enabled": all_settings.get("donation_enabled", False),
                    "title": all_settings.get("donation_title", "如果这篇文章对您有帮助，请考虑支持作者"),
                    "description": all_settings.get("donation_description", "您的支持是我创作的动力！"),
                    "qr_code_url": all_settings.get("donation_qr_code_url", ""),
                    "link_text": all_settings.get("donation_link_text", ""),
                    "link_url": all_settings.get("donation_link_url", ""),
                    "style_theme": all_settings.get("donation_style_theme", "elegant"),
                    "show_position": all_settings.get("donation_show_position", "article_end"),
                },
                "homepage": {
                    "mode": all_settings.get("homepage_mode", DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]),
                    "background_image_url": all_settings.get("homepage_background_image_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_image_url"]),
                    "background_video_url": all_settings.get("homepage_background_video_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_video_url"]),
                    "background_music_url": all_settings.get("homepage_background_music_url", DEFAULT_HOMEPAGE_SETTINGS["homepage_background_music_url"]),
                    "music_autoplay": all_settings.get("homepage_music_autoplay", DEFAULT_HOMEPAGE_SETTINGS["homepage_music_autoplay"]),
                },
                "sitemap": {
                    "enabled": all_settings.get("sitemap_enabled", False),
                }
            }
            
            # 将结构化设置存储到 request.state
            request.state.settings = settings_dict
            
            # 为了保持向后兼容性，同时将设置作为平铺字段存储到 request.state
            # 这样现有的 build_base_template_context 函数可以继续工作
            for key, value in all_settings.items():
                if not hasattr(request.state, key):
                    setattr(request.state, key, value)
            
            # 设置默认值（如果数据库中没有对应设置）
            for key, default_value in DEFAULT_BASE_SETTINGS.items():
                if not hasattr(request.state, key):
                    setattr(request.state, key, default_value)
            
            for key, default_value in DEFAULT_HOMEPAGE_SETTINGS.items():
                if not hasattr(request.state, key):
                    setattr(request.state, key, default_value)
            
        except Exception as e:
            # 如果设置加载失败，使用默认值，确保应用不会崩溃
            print(f"Warning: Failed to load settings in middleware: {e}")
            request.state.settings = {}
            
            # 设置基本的默认值
            for key, default_value in DEFAULT_BASE_SETTINGS.items():
                setattr(request.state, key, default_value)
            for key, default_value in DEFAULT_HOMEPAGE_SETTINGS.items():
                setattr(request.state, key, default_value)
        finally:
            # 确保通过 get_db() 打开的会话被正确关闭，避免连接池泄漏
            if db_gen is not None:
                try:
                    db_gen.close()
                except Exception:
                    pass
        
        # 继续处理请求
        response = await call_next(request)
        return response
