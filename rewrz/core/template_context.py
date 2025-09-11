"""
模板基础上下文构建工具

提供构建模板渲染所需的通用基础上下文字段，避免在各路由中重复注入。
"""
from fastapi import Request

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
    # 新增：社交与页脚相关
    "social_links": [],  # [{ icon: str, url: str }, ...]
    "custom_footer_text": "",
    "icp_beian": "",
    "gongan_beian": "",
    "rss_enabled": True,
    "copyright_info": "",
}

# 主页个性化设置的集中默认值，供全局读取与回退使用
DEFAULT_HOMEPAGE_SETTINGS = {
    "homepage_mode": "default",
    "homepage_background_image_url": "",
    "homepage_background_video_url": "",
    "homepage_background_music_url": "",
    "homepage_music_autoplay": False,
}


def build_base_template_context(request: Request) -> dict:
    """
    构建模板基础上下文字典，包含所有页面共享的全局字段
    """
    return {
        "atmosphere_class": getattr(request.state, "atmosphere_class", ""),
        "site_title": getattr(request.state, "site_title", DEFAULT_BASE_SETTINGS["site_title"]),
        "tagline": getattr(request.state, "tagline", DEFAULT_BASE_SETTINGS["tagline"]),
        "noindex_site": getattr(request.state, "noindex_site", DEFAULT_BASE_SETTINGS["noindex_site"]),
        "block_ai_crawlers": getattr(request.state, "block_ai_crawlers", DEFAULT_BASE_SETTINGS["block_ai_crawlers"]),
        # 新增：站点展示相关（logo / favicon）
        "site_logo_light": getattr(request.state, "site_logo_light", DEFAULT_BASE_SETTINGS["site_logo_light"]),
        "site_logo_dark": getattr(request.state, "site_logo_dark", DEFAULT_BASE_SETTINGS["site_logo_dark"]),
        "favicon": getattr(request.state, "favicon", DEFAULT_BASE_SETTINGS["favicon"]),
        # 新增：社交与页脚相关
        "social_links": getattr(request.state, "social_links", DEFAULT_BASE_SETTINGS["social_links"]),
        "custom_footer_text": getattr(request.state, "custom_footer_text", DEFAULT_BASE_SETTINGS["custom_footer_text"]),
        "icp_beian": getattr(request.state, "icp_beian", DEFAULT_BASE_SETTINGS["icp_beian"]),
        "gongan_beian": getattr(request.state, "gongan_beian", DEFAULT_BASE_SETTINGS["gongan_beian"]),
        "rss_enabled": getattr(request.state, "rss_enabled", DEFAULT_BASE_SETTINGS["rss_enabled"]),
        "copyright_info": getattr(request.state, "copyright_info", DEFAULT_BASE_SETTINGS["copyright_info"]),
    }