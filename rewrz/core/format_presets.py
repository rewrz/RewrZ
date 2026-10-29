"""微动态与诗词的格式内样式预设。

预设只改变格式内部的排版与样式，不跨格式复用文章模板，
也不影响聚合页列表卡片。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

DEFAULT_STYLE_PRESET = "auto"

# 微动态预设：auto 会按内容特征自动落到具体预设。
MICRO_STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "auto": {
        "label": "自动匹配",
        "description": "图片较多时自动使用图集排版，含引用块时自动使用引言排版，其余保持简版。",
    },
    "plain": {
        "label": "简版（Plain）",
        "description": "紧凑的日常动态排版，适合纯文字短内容。",
    },
    "gallery": {
        "label": "图集（Gallery）",
        "description": "突出配图的网格排版，适合多图动态。",
    },
    "quote": {
        "label": "引言（Quote）",
        "description": "放大引用块与正文留白，适合观点摘录与语录。",
    },
}

POEM_STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "auto": {
        "label": "自动匹配",
        "description": "默认使用古典排版，后续可在编辑器中手动切换。",
    },
    "classic": {
        "label": "古典（Classic）",
        "description": "宋体正文与宽松行距，适合格律诗与古体诗。",
    },
    "modern": {
        "label": "现代（Modern）",
        "description": "无衬线正文与舒展留白，适合现代诗与散文诗。",
    },
    "ci": {
        "label": "词牌（Ci）",
        "description": "居中窄栏与更大行距，适合词、令与短句排版。",
    },
}

INTENT_STYLE_PRESET_REGISTRY: Dict[str, Dict[str, Dict[str, str]]] = {
    "micro": MICRO_STYLE_PRESETS,
    "poem": POEM_STYLE_PRESETS,
}

_IMAGE_TAG_RE = re.compile(r"<img\s", re.IGNORECASE)
_BLOCKQUOTE_RE = re.compile(r"<blockquote", re.IGNORECASE)


def normalize_style_preset_for_intent(intent_slug: Optional[str], raw_value: Optional[str]) -> str:
    """把预设收敛到当前内容意图允许的集合内；其他意图直接回落到 auto。"""
    intent = str(intent_slug or "").strip().lower()
    registry = INTENT_STYLE_PRESET_REGISTRY.get(intent)
    if not registry:
        return DEFAULT_STYLE_PRESET
    candidate = str(raw_value or "").strip().lower()
    if candidate in registry:
        return candidate
    return DEFAULT_STYLE_PRESET


def normalize_style_preset_value(raw_value: Optional[str]) -> str:
    """不区分内容意图时，只要命中任一预设集合即保留，否则回落到 auto。"""
    candidate = str(raw_value or "").strip().lower()
    for registry in INTENT_STYLE_PRESET_REGISTRY.values():
        if candidate in registry:
            return candidate
    return DEFAULT_STYLE_PRESET


def _detect_micro_preset(content_html: Optional[str]) -> str:
    """按渲染后的 HTML 判断微动态自动预设。"""
    html = content_html or ""
    if len(_IMAGE_TAG_RE.findall(html)) >= 2:
        return "gallery"
    if _BLOCKQUOTE_RE.search(html):
        return "quote"
    return "plain"


def resolve_micro_style_preset(raw_value: Optional[str], content_html: Optional[str]) -> str:
    preset = normalize_style_preset_for_intent("micro", raw_value)
    if preset == "auto":
        return _detect_micro_preset(content_html)
    return preset


def resolve_poem_style_preset(raw_value: Optional[str]) -> str:
    preset = normalize_style_preset_for_intent("poem", raw_value)
    if preset == "auto":
        return "classic"
    return preset


def get_style_preset_options() -> List[Dict[str, str]]:
    """返回后台预设下拉选项，附带所属内容意图供前端按类型过滤。"""
    options: List[Dict[str, str]] = []
    for intent, registry in INTENT_STYLE_PRESET_REGISTRY.items():
        for key, meta in registry.items():
            options.append(
                {
                    "value": key,
                    "intent": intent,
                    "label": str(meta.get("label", key)),
                    "description": str(meta.get("description", "")),
                }
            )
    return options
