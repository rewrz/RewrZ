import re
from typing import Optional

from markdown import markdown


VALID_EDITOR_MODES = {"markdown", "html"}
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists", "nl2br")


def render_markdown_html(content_markdown: Optional[str]) -> str:
    """
    统一 Markdown -> HTML 渲染策略，尽量与编辑器预览观感保持一致。

    - extra: 支持表格、围栏代码块等常见语法
    - sane_lists: 列表渲染更稳定
    - nl2br: 单换行也保留为可见换行
    """
    markdown_content = content_markdown or ""
    if not markdown_content.strip():
        return ""
    return markdown(markdown_content, extensions=list(MARKDOWN_RENDER_EXTENSIONS))


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


def get_effective_content_html(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    html_content = (content_html or "").strip()
    if html_content:
        return html_content

    return render_markdown_html(content_markdown)


def html_to_plain_text(content_html: Optional[str]) -> str:
    html_content = content_html or ""
    if not html_content:
        return ""
    plain_text = re.sub(r"<[^>]+>", " ", html_content)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    return plain_text


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


def get_effective_plain_text(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    markdown_text = markdown_to_plain_text(content_markdown)
    if markdown_text:
        return markdown_text
    return html_to_plain_text(content_html)
