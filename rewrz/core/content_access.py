"""
内容访问相关工具

集中处理以下能力：
1. [hide]...[/hide] 评论后可见内容解析与渲染
2. 评论解锁 Cookie 命名约定
"""

from __future__ import annotations

import re
from typing import Optional

from markdown import markdown


HIDE_BLOCK_RE = re.compile(r"\[hide\](.*?)\[/hide\]", re.IGNORECASE | re.DOTALL)


def get_comment_unlock_cookie_name(post_id: int) -> str:
    return f"commented_post_{post_id}"


def has_hide_blocks(content_markdown: Optional[str]) -> bool:
    if not content_markdown:
        return False
    return HIDE_BLOCK_RE.search(content_markdown) is not None


def extract_hide_block(content_markdown: Optional[str], index: int) -> Optional[str]:
    if not content_markdown or index < 0:
        return None
    matches = list(HIDE_BLOCK_RE.finditer(content_markdown))
    if index >= len(matches):
        return None
    return (matches[index].group(1) or "").strip()


def build_hidden_placeholder_html(post_id: int, block_index: int) -> str:
    placeholder_id = f"hidden-content-{post_id}-{block_index}"
    return (
        f'<div id="{placeholder_id}" class="my-4 rounded-lg border border-dashed border-indigo-300 bg-indigo-50 p-4">'
        '<p class="mb-3 text-sm text-gray-700">此处内容仅对评论过本文的访客可见。</p>'
        f'<button class="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700" '
        f'hx-post="/api/v1/reveal/{post_id}?index={block_index}" '
        f'hx-target="#{placeholder_id}" hx-swap="outerHTML">'
        "我已评论，点击查看"
        "</button>"
        "</div>"
    )


def render_markdown_with_hide_blocks(
    content_markdown: Optional[str],
    post_id: int,
    can_view_hidden: bool,
) -> str:
    """
    将包含 [hide] 块的 Markdown 渲染为 HTML。

    - 未解锁：输出占位符（可通过 HTMX 点击后异步 reveal）
    - 已解锁：正常渲染隐藏块内部 Markdown
    """
    if not content_markdown:
        return ""

    if not has_hide_blocks(content_markdown):
        return markdown(content_markdown)

    rendered_parts = []
    last_end = 0
    block_index = 0

    for match in HIDE_BLOCK_RE.finditer(content_markdown):
        normal_segment = content_markdown[last_end : match.start()]
        if normal_segment.strip():
            rendered_parts.append(markdown(normal_segment))

        hidden_segment = (match.group(1) or "").strip()
        if can_view_hidden:
            rendered_parts.append(markdown(hidden_segment))
        else:
            rendered_parts.append(build_hidden_placeholder_html(post_id, block_index))

        last_end = match.end()
        block_index += 1

    tail_segment = content_markdown[last_end:]
    if tail_segment.strip():
        rendered_parts.append(markdown(tail_segment))

    return "".join(rendered_parts)

