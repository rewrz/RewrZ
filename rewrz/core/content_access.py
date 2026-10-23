"""
内容访问相关工具

集中处理以下能力：
1. [hide]...[/hide] 评论后可见内容解析与渲染
2. 评论解锁 Cookie 与密码保护 Cookie 的命名与校验
3. 内容公开可访问性判定（发布状态、私密、密码）
"""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Optional

from .config import settings
from .content_utils import render_markdown_html
from .time_utils import utc_now_naive


HIDE_BLOCK_RE = re.compile(r"\[hide\](.*?)\[/hide\]", re.IGNORECASE | re.DOTALL)


def get_comment_unlock_cookie_name(post_id: int) -> str:
    return f"commented_post_{post_id}"


def get_post_access_cookie_name(post_id: int) -> str:
    return f"post_access_{post_id}"


def build_post_access_cookie_value(post_id: int, hashed_password: str) -> str:
    payload = f"{post_id}:{hashed_password}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_valid_password_cookie(request, post_obj) -> bool:
    """校验访客是否已通过密码保护内容的访问密码。"""
    if post_obj is None or not getattr(post_obj, "password", None):
        return False

    cookie_value = request.cookies.get(get_post_access_cookie_name(post_obj.id))
    if not cookie_value:
        return False

    expected = build_post_access_cookie_value(post_obj.id, post_obj.password)
    return secrets.compare_digest(cookie_value, expected)


def is_publicly_accessible(request, post_obj, *, is_admin: bool = False) -> bool:
    """
    判断当前访客能否访问该内容的公开部分。

    私密内容仅管理员可访问；密码内容需已通过密码校验；未发布内容一律不可访问。
    """
    if post_obj is None:
        return False
    if is_admin:
        return True
    if str(getattr(post_obj, "status", "") or "") != "published":
        return False
    published_at = getattr(post_obj, "published_at", None)
    if not published_at or published_at > utc_now_naive():
        # 发布时间为空或位于未来时视为尚未上线（未来时间即定时发布）
        return False

    visibility = str(getattr(post_obj, "visibility", "public") or "public").strip().lower()
    if visibility == "private":
        return False
    if visibility == "password":
        return has_valid_password_cookie(request, post_obj)
    return True


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


def strip_hide_blocks(content_markdown: Optional[str]) -> str:
    if not content_markdown:
        return ""
    return HIDE_BLOCK_RE.sub("", content_markdown)


def build_hidden_placeholder_html(post_id: int, block_index: int) -> str:
    placeholder_id = f"hidden-content-{post_id}-{block_index}"
    return (
        f'<div id="{placeholder_id}" class="content-hide-placeholder my-4">'
        '<p class="content-hide-placeholder__copy">'
        '<i class="fas fa-comment-dots content-hide-placeholder__icon" aria-hidden="true"></i>'
        '<span>此处内容仅对评论过本文的访客可见。</span>'
        '</p>'
        f'<button class="content-hide-placeholder__button" '
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
        return render_markdown_html(content_markdown)

    rendered_parts = []
    last_end = 0
    block_index = 0

    for match in HIDE_BLOCK_RE.finditer(content_markdown):
        normal_segment = content_markdown[last_end : match.start()]
        if normal_segment.strip():
            rendered_parts.append(render_markdown_html(normal_segment))

        hidden_segment = (match.group(1) or "").strip()
        if can_view_hidden:
            rendered_parts.append(render_markdown_html(hidden_segment))
        else:
            rendered_parts.append(build_hidden_placeholder_html(post_id, block_index))

        last_end = match.end()
        block_index += 1

    tail_segment = content_markdown[last_end:]
    if tail_segment.strip():
        rendered_parts.append(render_markdown_html(tail_segment))

    return "".join(rendered_parts)
