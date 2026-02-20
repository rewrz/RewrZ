"""页面模板注册与解析工具。"""

from __future__ import annotations

from typing import Dict, List

DEFAULT_PAGE_TEMPLATE = "default"

PAGE_TEMPLATE_REGISTRY: Dict[str, Dict[str, str]] = {
    "default": {
        "label": "默认页面（全宽）",
        "description": "WordPress 常见默认页风格，适合通用内容展示。",
        "template_file": "page.html",
    },
    "about": {
        "label": "关于页面（Profile）",
        "description": "二次元角色档案风格，适合关于我/关于站点。",
        "template_file": "page_about.html",
    },
    "links": {
        "label": "友情链接（Blogroll）",
        "description": "卡片式友链风格，适合站点导航与资源列表。",
        "template_file": "page_links.html",
    },
    "timeline": {
        "label": "时间轴（Archives）",
        "description": "WordPress 常见历程/归档页风格，适合大事记内容。",
        "template_file": "page_timeline.html",
    },
    "landing": {
        "label": "落地页（Landing）",
        "description": "大视觉首屏风格，适合活动页与引导页。",
        "template_file": "page_landing.html",
    },
}


def normalize_page_template(raw_value: str | None) -> str:
    candidate = str(raw_value or "").strip().lower()
    if candidate in PAGE_TEMPLATE_REGISTRY:
        return candidate
    return DEFAULT_PAGE_TEMPLATE


def resolve_page_template_file(raw_value: str | None) -> str:
    key = normalize_page_template(raw_value)
    return PAGE_TEMPLATE_REGISTRY.get(key, PAGE_TEMPLATE_REGISTRY[DEFAULT_PAGE_TEMPLATE])["template_file"]


def get_page_template_options() -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for key, meta in PAGE_TEMPLATE_REGISTRY.items():
        options.append(
            {
                "value": key,
                "label": meta.get("label", key),
                "description": meta.get("description", ""),
            }
        )
    return options
