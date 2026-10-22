import re
from functools import lru_cache
from typing import Optional

from markdown import markdown


VALID_EDITOR_MODES = {"markdown", "html"}
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists", "nl2br")


@lru_cache(maxsize=128)
def _render_markdown_html_cached(markdown_content: str) -> str:
    if not markdown_content.strip():
        return ""
    return markdown(markdown_content, extensions=list(MARKDOWN_RENDER_EXTENSIONS))


def render_markdown_html(content_markdown: Optional[str]) -> str:
    """
    统一 Markdown -> HTML 渲染策略，尽量与编辑器预览观感保持一致。

    - extra: 支持表格、围栏代码块等常见语法
    - sane_lists: 列表渲染更稳定
    - nl2br: 单换行也保留为可见换行
    """
    return _render_markdown_html_cached(content_markdown or "")


def normalize_editor_mode(value: Optional[str], fallback: str = "markdown") -> str:
    mode = (value or "").strip().lower()
    if mode in VALID_EDITOR_MODES:
        return mode
    return fallback if fallback in VALID_EDITOR_MODES else "markdown"


def infer_editor_mode(
    requested_mode: Optional[str],
    content_markdown: Optional[str],
    content_html: Optional[str],
    fallback: str = "markdown",
) -> str:
    normalized_requested = normalize_editor_mode(requested_mode, fallback="")
    if normalized_requested in VALID_EDITOR_MODES:
        return normalized_requested

    markdown_has_content = bool((content_markdown or "").strip())
    html_has_content = bool((content_html or "").strip())

    if html_has_content and not markdown_has_content:
        return "html"
    if markdown_has_content and not html_has_content:
        return "markdown"
    return normalize_editor_mode(fallback)


@lru_cache(maxsize=128)
def _get_effective_content_html_cached(content_markdown: str, content_html: str) -> str:
    html_content = content_html.strip()
    if html_content:
        return html_content

    return render_markdown_html(content_markdown)


def get_effective_content_html(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    return _get_effective_content_html_cached(content_markdown or "", content_html or "")


@lru_cache(maxsize=128)
def html_to_plain_text(content_html: Optional[str]) -> str:
    raw_html = content_html or ""
    if not raw_html:
        return ""
    plain_text = re.sub(r"<[^>]+>", " ", raw_html)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    return plain_text


@lru_cache(maxsize=128)
def markdown_to_plain_text(content_markdown: Optional[str]) -> str:
    markdown_content = content_markdown or ""
    if not markdown_content:
        return ""
    plain_text = markdown_content
    plain_text = re.sub(r"```[\s\S]*?```", " ", plain_text)
    plain_text = re.sub(r"`[^`]*`", " ", plain_text)
    plain_text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", plain_text)
    plain_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain_text)
    plain_text = re.sub(r"^#{1,6}\s+", "", plain_text, flags=re.MULTILINE)
    plain_text = re.sub(r"[*_~>\-]+", " ", plain_text)
    plain_text = re.sub(r"<[^>]+>", " ", plain_text)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    return plain_text


@lru_cache(maxsize=128)
def _get_effective_plain_text_cached(content_markdown: str, content_html: str) -> str:
    html_content = content_html.strip()
    if html_content:
        plain_text = html_to_plain_text(html_content)
        if plain_text:
            return plain_text

    markdown_content = content_markdown.strip()
    if markdown_content:
        rendered_html = render_markdown_html(markdown_content)
        plain_text = html_to_plain_text(rendered_html)
        if plain_text:
            return plain_text
        fallback_text = markdown_to_plain_text(markdown_content)
        if fallback_text:
            return fallback_text

    return ""


def get_effective_plain_text(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    return _get_effective_plain_text_cached(content_markdown or "", content_html or "")
