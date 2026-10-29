import re
from functools import lru_cache
from typing import Optional

from markdown import markdown


VALID_EDITOR_MODES = {"markdown", "html"}
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists", "nl2br")
TASK_LIST_ITEM_PATTERN = re.compile(r"<li>\s*\[([ xX])\]\s*")
# Markdown 区块指令：:::名称 [参数]，闭合为单独一行 :::
DIRECTIVE_OPEN_PATTERN = re.compile(r"^:::(\w+)(?:\s+([\w-]+))?$")
DIRECTIVE_CLOSE_LINE = ":::"


def _render_task_list_items(html_content: str) -> str:
    """把 Markdown 任务列表的 [x] / [ ] 标记渲染为只读复选框。"""
    if "[" not in html_content:
        return html_content

    def replace_item(match: re.Match) -> str:
        checked = " checked" if match.group(1).lower() == "x" else ""
        return f'<li class="task-list-item"><input type="checkbox" class="task-list-checkbox" disabled{checked}> '

    return TASK_LIST_ITEM_PATTERN.sub(replace_item, html_content)


def _render_plain_markdown(text: str) -> str:
    """渲染不含区块指令的 Markdown 片段。"""
    if not text.strip():
        return ""
    return markdown(text, extensions=list(MARKDOWN_RENDER_EXTENSIONS))


def _split_directive_columns(inner: str) -> tuple[str, str]:
    """拆分 columns 指令内的 left / right 子块，缺省时按空列处理。"""
    columns: dict[str, str] = {}
    for kind, payload in _parse_directive_segments(inner):
        if kind != "block":
            continue
        if payload["name"] in {"left", "right"} and payload["name"] not in columns:
            columns[payload["name"]] = payload["inner"]
    return columns.get("left", ""), columns.get("right", "")


def _render_directive_block(name: str, arg: str, inner: str) -> str:
    """把单个区块指令渲染为带样式的 HTML 片段。"""
    inner_html = _render_task_list_items(_render_plain_markdown(inner))

    if name == "wide":
        return f'<div class="md-block md-block-wide">{inner_html}</div>'

    if name == "gallery":
        # 图集只保留图片本身，避免 Markdown 段落与换行标签混进网格布局
        images = re.findall(
            r"<a\b[^>]*>\s*<img\b[^>]*>\s*</a>|<img\b[^>]*>",
            inner_html,
            re.IGNORECASE,
        )
        if images:
            pair_class = " md-gallery-pair" if len(images) == 2 else ""
            return f'<div class="md-block md-block-gallery{pair_class}">{"".join(images)}</div>'
        return f'<div class="md-block md-block-gallery">{inner_html}</div>'

    if name == "quote":
        return f'<figure class="md-block md-block-quote"><blockquote>{inner_html}</blockquote></figure>'

    if name == "notice":
        notice_class = "is-warn" if arg in {"warn", "warning"} else "is-info"
        return f'<aside class="md-block md-block-notice {notice_class}">{inner_html}</aside>'

    if name == "columns":
        left_inner, right_inner = _split_directive_columns(inner)
        if not left_inner and not right_inner:
            return inner_html
        left_html = _render_task_list_items(_render_plain_markdown(left_inner))
        right_html = _render_task_list_items(_render_plain_markdown(right_inner))
        return (
            '<div class="md-block md-block-columns">'
            f'<div class="md-column">{left_html}</div>'
            f'<div class="md-column">{right_html}</div>'
            "</div>"
        )

    if name == "timeline":
        list_match = re.search(r"<ul>(.*?)</ul>", inner_html, re.DOTALL)
        if list_match:
            return f'<ul class="md-block md-block-timeline">{list_match.group(1)}</ul>'
        return f'<div class="md-block md-block-timeline">{inner_html}</div>'

    if name == "table":
        return f'<div class="md-block md-block-table">{inner_html}</div>'

    # 未识别的指令不破坏内容，直接返回内部渲染结果
    return inner_html


def _parse_directive_segments(text: str) -> list[tuple[str, object]]:
    """把文本拆成普通文本段与区块指令段，代码围栏内的 ::: 不参与解析。"""
    lines = text.splitlines(keepends=True)
    segments: list[tuple[str, object]] = []
    buffer: list[str] = []
    index = 0
    in_code_fence = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            buffer.append(line)
            index += 1
            continue

        # 指令必须从行首书写，避免把缩进代码块里的 ::: 误判为区块指令
        match = None if in_code_fence else DIRECTIVE_OPEN_PATTERN.match(line.rstrip())
        if match is None:
            buffer.append(line)
            index += 1
            continue

        if buffer:
            segments.append(("text", "".join(buffer)))
            buffer = []

        name = match.group(1).lower()
        arg = (match.group(2) or "").lower()
        inner_lines: list[str] = []
        depth = 1
        cursor = index + 1
        inner_code_fence = False

        while cursor < len(lines):
            inner_stripped = lines[cursor].strip()
            inner_line = lines[cursor].rstrip()
            if inner_stripped.startswith("```"):
                inner_code_fence = not inner_code_fence
            if not inner_code_fence:
                if inner_line == DIRECTIVE_CLOSE_LINE:
                    depth -= 1
                    if depth == 0:
                        break
                elif DIRECTIVE_OPEN_PATTERN.match(inner_line):
                    depth += 1
            inner_lines.append(lines[cursor])
            cursor += 1

        if cursor >= len(lines):
            # 未闭合的指令按普通文本处理，避免吞掉正文
            buffer.append(line)
            index += 1
            continue

        segments.append(("block", {"name": name, "arg": arg, "inner": "".join(inner_lines)}))
        index = cursor + 1

    if buffer:
        segments.append(("text", "".join(buffer)))
    return segments


def _render_markdown_with_directives(content_markdown: str) -> str:
    """渲染带 ::: 区块指令的 Markdown，指令之外的文本仍按普通 Markdown 渲染。"""
    parts: list[str] = []
    for kind, payload in _parse_directive_segments(content_markdown):
        if kind == "text":
            parts.append(_render_task_list_items(_render_plain_markdown(str(payload))))
        else:
            block = payload  # type: ignore[assignment]
            parts.append(_render_directive_block(block["name"], block["arg"], block["inner"]))
    return "".join(parts)


@lru_cache(maxsize=128)
def _render_markdown_html_cached(markdown_content: str) -> str:
    if not markdown_content.strip():
        return ""
    if ":::" in markdown_content:
        return _render_markdown_with_directives(markdown_content)
    rendered = _render_plain_markdown(markdown_content)
    return _render_task_list_items(rendered)


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
    # 区块指令的 ::: 行只用于排版，不进入纯文本口径
    plain_text = re.sub(r"^:::\w*(?:\s+[\w-]+)?$", "", plain_text, flags=re.MULTILINE)
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
