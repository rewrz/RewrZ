"""
内容类型（Content Type）统一规则。

核心意图仅保留：
- article
- micro
- poem
"""

from __future__ import annotations

from typing import Iterable, Optional


INTENT_SLUGS: tuple[str, ...] = ("article", "micro", "poem")
INTENT_PRIORITY: tuple[str, ...] = ("micro", "poem", "article")
INTENT_NAME_MAP: dict[str, str] = {
    "article": "标准文章",
    "micro": "微博",
    "poem": "诗词歌赋",
}

# 严格归一化：仅接受当前内容类型集合
INTENT_ALIAS_TO_CANONICAL: dict[str, str] = {
    "article": "article",
    "micro": "micro",
    "poem": "poem",
}

# 路由入参归一化（仅接受规范路径）
PUBLIC_ROUTE_ALIAS_TO_CANONICAL: dict[str, str] = {
    "article": "article",
    "micro": "micro",
    "poem": "poem",
}

# 文章详情路径展示段（与 canonical 一致）
CANONICAL_TO_PUBLIC_SEGMENT: dict[str, str] = {
    "article": "article",
    "micro": "micro",
    "poem": "poem",
}


def normalize_intent_slug(raw_slug: Optional[str]) -> Optional[str]:
    if raw_slug is None:
        return None
    text = str(raw_slug).strip().lower()
    if not text:
        return None
    return INTENT_ALIAS_TO_CANONICAL.get(text)


def normalize_public_intent_slug(raw_slug: Optional[str]) -> Optional[str]:
    if raw_slug is None:
        return None
    text = str(raw_slug).strip().lower()
    if not text:
        return None
    return PUBLIC_ROUTE_ALIAS_TO_CANONICAL.get(text)


def choose_primary_intent_slug(format_slugs: Iterable[str]) -> str:
    normalized = {
        intent
        for intent in (normalize_intent_slug(slug) for slug in format_slugs)
        if intent in INTENT_SLUGS
    }
    for candidate in INTENT_PRIORITY:
        if candidate in normalized:
            return candidate
    return "article"


def to_public_post_segment(intent_slug: str) -> str:
    canonical = normalize_intent_slug(intent_slug) or "article"
    return CANONICAL_TO_PUBLIC_SEGMENT.get(canonical, "article")


