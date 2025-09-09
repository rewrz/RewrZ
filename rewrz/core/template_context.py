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
    }