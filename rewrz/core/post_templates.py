"""文章详情整页模板注册与解析。

三条轴的边界：
- 内容意图（formats）决定语义与路由；
- post_template 只影响标准文章的详情整页版式；
- style_preset 只影响微动态/诗词格式内的样式预设。

微动态与诗词不使用本注册表，路由始终走格式专属布局。
"""

from __future__ import annotations

from typing import Dict, List, Optional

DEFAULT_POST_TEMPLATE = "auto"

# 每个模板只允许附带一个模板 CSS 与一个按需 JS，标准模板复用共享详情样式。
POST_TEMPLATE_REGISTRY: Dict[str, Dict[str, object]] = {
    "auto": {
        "label": "自动（标准阅读）",
        "description": "跟随默认文章版式，保持与旧文章一致的阅读体验。",
        "usage": "正文按标题分节、图片单独成段即可；后续可手动切换为展览或长文版式。",
        "resolves_to": "standard",
        "partial": "partials/post_templates/standard.html",
        "css": None,
        "js": None,
    },
    "standard": {
        "label": "标准文章（Standard）",
        "description": "默认文章卡片版式，适合大多数随笔、教程与资讯。",
        "usage": "用二级标题分节，正文写段落、列表或表格；首屏展示标题、摘要、作者与分类标签。",
        "resolves_to": None,
        "partial": "partials/post_templates/standard.html",
        "css": None,
        "js": None,
    },
    "gallery": {
        "label": "图文展览（Gallery）",
        "description": "沉浸式图文版式，适合摄影、图集与以图片为主的文章。",
        "usage": "用 ## 写章节，图片单独成段并把作品名写进图片说明：![作品名](图片地址)，模板会自动放大图片、生成图注并支持点击放大。",
        "resolves_to": None,
        "partial": "partials/post_templates/gallery.html",
        "css": "css/post-template-gallery.css",
        "js": "js/post-template-gallery.js",
    },
    "longform": {
        "label": "深度长文（Longform）",
        "description": "窄栏长文版式，适合深度分析、连载与长篇叙事。",
        "usage": "用二级标题分节，段落保持适中长度；版式会自动收窄栏宽、放大行距并插入章节分隔线。",
        "resolves_to": None,
        "partial": "partials/post_templates/longform.html",
        "css": "css/post-template-longform.css",
        "js": None,
    },
}


def normalize_post_template(raw_value: Optional[str]) -> str:
    """把任意输入收敛到注册表内的模板键。"""
    candidate = str(raw_value or "").strip().lower()
    if candidate in POST_TEMPLATE_REGISTRY:
        return candidate
    return DEFAULT_POST_TEMPLATE


def resolve_post_template_key(raw_value: Optional[str]) -> str:
    """解析最终实际渲染的模板键（auto 会落到具体模板）。"""
    key = normalize_post_template(raw_value)
    resolved = POST_TEMPLATE_REGISTRY[key].get("resolves_to")
    if isinstance(resolved, str) and resolved in POST_TEMPLATE_REGISTRY:
        return resolved
    return key


def resolve_post_template(raw_value: Optional[str]) -> Dict[str, object]:
    """返回渲染所需的模板信息（partial、css、js）。"""
    key = resolve_post_template_key(raw_value)
    meta = POST_TEMPLATE_REGISTRY[key]
    return {
        "key": key,
        "label": meta.get("label", key),
        "partial": meta.get("partial"),
        "css": meta.get("css"),
        "js": meta.get("js"),
    }


def get_post_template_options() -> List[Dict[str, str]]:
    """返回后台下拉可用的模板选项。"""
    options: List[Dict[str, str]] = []
    for key, meta in POST_TEMPLATE_REGISTRY.items():
        options.append(
            {
                "value": key,
                "label": str(meta.get("label", key)),
                "description": str(meta.get("description", "")),
                "usage": str(meta.get("usage", "")),
            }
        )
    return options
