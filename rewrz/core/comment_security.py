"""评论内容安全处理。

统一评论 HTML 白名单、Markdown 转换与作者主页链接校验，
确保公开提交、后台导入和模板渲染使用同一套安全策略。
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

import bleach
from markdown import markdown

# 评论允许的 HTML 标签与属性，与公开评论接口保持一致。
ALLOWED_COMMENT_TAGS = ["a", "strong", "em", "code", "p", "br"]
ALLOWED_COMMENT_ATTRIBUTES = {"a": ["href", "title"]}


def sanitize_comment_content(raw_content: Optional[str]) -> str:
    """将评论原文按 Markdown 渲染后执行严格的 HTML 白名单过滤。"""
    text = str(raw_content or "").strip()
    if not text:
        return ""
    return bleach.clean(
        markdown(text),
        tags=ALLOWED_COMMENT_TAGS,
        attributes=ALLOWED_COMMENT_ATTRIBUTES,
        strip=True,
    )


def sanitize_comment_html(raw_html: Optional[str]) -> str:
    """仅对已渲染的评论 HTML 做白名单过滤，用于模板输出兜底。"""
    text = str(raw_html or "").strip()
    if not text:
        return ""
    return bleach.clean(
        text,
        tags=ALLOWED_COMMENT_TAGS,
        attributes=ALLOWED_COMMENT_ATTRIBUTES,
        strip=True,
    )


def normalize_comment_author_url(raw_url: Optional[str]) -> Optional[str]:
    """校验评论作者主页，只允许 http/https 绝对地址。"""
    text = str(raw_url or "").strip()
    if not text:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        return None

    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.netloc or parsed.username or parsed.password:
        return None
    return text
