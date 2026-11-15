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
# 隐藏块先替换成单行哨兵，让整篇 Markdown 一次性解析，避免 ::: 指令被切断
HIDE_SENTINEL_PREFIX = "@@REWRZ_HIDE_BLOCK_"
HIDE_SENTINEL_RE = re.compile(
    r"(?:<p>\s*)?@@REWRZ_HIDE_BLOCK_(\d+)@@(?:\s*<br\s*/?>)?\s*(?:</p>)?",
    re.IGNORECASE,
)
# 引用式链接与脚注定义，隐藏段单独渲染时需要复用整篇的定义
LINK_DEFINITION_RE = re.compile(r"^\[[^\]]+\]:\s+\S+.*$", re.MULTILINE)


# 前缀集中定义：详情页缓存用同一批常量排除敏感 Cookie，避免两处拼写漂移
COMMENT_UNLOCK_COOKIE_PREFIX = "commented_post_"
POST_ACCESS_COOKIE_PREFIX = "post_access_"


def get_comment_unlock_cookie_name(post_id: int) -> str:
    return f"{COMMENT_UNLOCK_COOKIE_PREFIX}{post_id}"


def get_post_access_cookie_name(post_id: int) -> str:
    return f"{POST_ACCESS_COOKIE_PREFIX}{post_id}"


def build_post_access_cookie_value(post_id: int, hashed_password: str) -> str:
    payload = f"{post_id}:{hashed_password}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_comment_unlock_cookie_value(post_id: int) -> str:
    """评论解锁凭证由站点密钥派生，避免明文 true 被任意伪造。"""
    payload = f"comment-unlock:{post_id}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_valid_comment_unlock_cookie(request, post_id: int) -> bool:
    """校验访客是否确实通过发表评论取得了当前文章的解锁凭证。"""
    cookie_value = request.cookies.get(get_comment_unlock_cookie_name(post_id))
    if not cookie_value:
        return False
    expected = build_comment_unlock_cookie_value(post_id)
    return secrets.compare_digest(cookie_value, expected)


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


def count_hide_blocks(content_markdown: Optional[str]) -> int:
    """统计 [hide] 块数量，用于评论区提示“评论后可解锁隐藏内容”。"""
    if not content_markdown:
        return 0
    return len(HIDE_BLOCK_RE.findall(content_markdown))


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

    matches = list(HIDE_BLOCK_RE.finditer(content_markdown))
    if not matches:
        return render_markdown_html(content_markdown)

    # 整篇一次性渲染：隐藏块用哨兵占位，::: 版式块与引用定义不会被分段切断
    source_parts: list[str] = []
    hidden_blocks: list[str] = []
    last_end = 0
    for index, match in enumerate(matches):
        source_parts.append(content_markdown[last_end:match.start()])
        source_parts.append(f"\n\n{HIDE_SENTINEL_PREFIX}{index}@@\n\n")
        hidden_blocks.append((match.group(1) or "").strip())
        last_end = match.end()
    source_parts.append(content_markdown[last_end:])

    rendered = render_markdown_html("".join(source_parts))
    definitions = "\n".join(LINK_DEFINITION_RE.findall(content_markdown))

    def replace_sentinel(match: re.Match) -> str:
        block_index = int(match.group(1))
        if not can_view_hidden:
            return build_hidden_placeholder_html(post_id, block_index)
        hidden_segment = hidden_blocks[block_index]
        if definitions:
            # 隐藏段单独渲染时补上整篇的链接/脚注定义，避免跨段引用失效
            hidden_segment = f"{hidden_segment}\n\n{definitions}"
        return render_markdown_html(hidden_segment)

    return HIDE_SENTINEL_RE.sub(replace_sentinel, rendered)
