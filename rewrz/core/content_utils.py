import re
from functools import lru_cache
from html import unescape
from typing import Optional

import bleach
from markdown import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import SimpleTagInlineProcessor


VALID_EDITOR_MODES = {"markdown", "html"}
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists", "nl2br", "attr_list")
VALID_CONTENT_RATINGS = ("general", "sensitive", "nsfw")
TASK_LIST_ITEM_PATTERN = re.compile(r"<li>\s*\[([ xX])\]\s*")
# 松散列表会被 Markdown 包成 <li><p>[ ] 文本</p></li>，需要单独识别
LOOSE_TASK_LIST_ITEM_PATTERN = re.compile(
    r"<li>\s*<p>\s*\[([ xX])\]\s*(.*?)</p>\s*",
    re.DOTALL,
)
# Markdown 区块指令：:::名称 [参数]，闭合为单独一行 :::
DIRECTIVE_OPEN_PATTERN = re.compile(r"^:::(\w+)(?:\s+([\w-]+))?$")
DIRECTIVE_CLOSE_LINE = ":::"
FENCE_LINE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
# 正文图片标签与尺寸档位：编辑器用 URL fragment 承载尺寸（#md-img-lg），
# 因为 Toast UI 在 Markdown/富文本往返时会丢弃 class 等非白名单属性。
HTML_IMAGE_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
HTML_SRC_ATTR_PATTERN = re.compile(r'(?<![\w:-])src\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
HTML_ALT_ATTR_PATTERN = re.compile(r'(?<![\w:-])alt\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
HTML_CLASS_ATTR_PATTERN = re.compile(r'(?<![\w:-])class\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
MARKDOWN_IMAGE_SIZE_FRAGMENT_PATTERN = re.compile(r"#md-img-(?:xs|sm|md|lg|full)$", re.IGNORECASE)
# 富文本编辑器常用 <p><br></p> 表示空行，渲染到前台会额外占一整行
EMPTY_PARAGRAPH_PATTERN = re.compile(
    r"<p(?:\s[^>]*)?>(?:\s|<br\b[^>]*>|&nbsp;|\u00a0)*</p>",
    re.IGNORECASE,
)
# 可比文本按块级标签断行，保证 diff 有真实的行结构
HTML_BLOCK_BOUNDARY_PATTERN = re.compile(
    r"</?(?:p|div|section|article|aside|header|footer|nav|blockquote|figure|figcaption|"
    r"h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|pre|hr|br)\b[^>]*>",
    re.IGNORECASE,
)


def _read_tag_attr(pattern: re.Pattern, tag: str) -> Optional[str]:
    """读取标签上的属性值，同时兼容单引号与双引号写法。"""
    match = pattern.search(tag)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _image_tag_to_text(tag: str) -> str:
    """把图片标签折叠成可用于 diff 的文本标记，保留图片地址但不比较尺寸片段。"""
    src = _read_tag_attr(HTML_SRC_ATTR_PATTERN, tag) or ""
    alt = _read_tag_attr(HTML_ALT_ATTR_PATTERN, tag) or ""
    src = MARKDOWN_IMAGE_SIZE_FRAGMENT_PATTERN.sub("", src)
    return f"![{alt}]({src})"


def _replace_image_size_fragment(match: re.Match) -> str:
    """把 src 里的 #md-img-* 片段转成对应的尺寸 class，并清理 URL 片段。"""
    tag = match.group(0)
    src_attr = HTML_SRC_ATTR_PATTERN.search(tag)
    if src_attr is None:
        return tag

    raw_src = src_attr.group(1) if src_attr.group(1) is not None else src_attr.group(2)
    fragment_match = MARKDOWN_IMAGE_SIZE_FRAGMENT_PATTERN.search(raw_src or "")
    if fragment_match is None:
        return tag

    size = fragment_match.group(0)[len("#md-img-"):].strip().lower()
    size_class = f"md-img-{size}"
    cleaned_src = raw_src[:fragment_match.start()]
    tag = f'{tag[:src_attr.start()]}src="{cleaned_src}"{tag[src_attr.end():]}'

    class_attr = HTML_CLASS_ATTR_PATTERN.search(tag)
    if class_attr is not None:
        class_value = class_attr.group(1) if class_attr.group(1) is not None else class_attr.group(2)
        class_names = [name for name in (class_value or "").split() if name]
        if size_class not in class_names:
            class_names.append(size_class)
        return f'{tag[:class_attr.start()]}class="{" ".join(class_names)}"{tag[class_attr.end():]}'

    closing = "/>" if tag.rstrip().endswith("/>") else ">"
    body = tag.rstrip()[:-len(closing)].rstrip()
    return f'{body} class="{size_class}" {closing}'


# 正文允许的标签与属性：覆盖 Markdown 渲染结果、图片尺寸、代码块、表格、
# 任务列表、提示块与常见媒体嵌入；style 与 on* 一律不放行。
CONTENT_ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code", "hr",
    "strong", "em", "del", "s", "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td",
    "video", "audio", "source", "iframe",
    "div", "span", "section", "aside", "details", "summary",
    "kbd", "mark", "sup", "sub", "input", "dl", "dt", "dd", "small",
]
CONTENT_ALLOWED_ATTRIBUTES = {
    "*": ["class"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "video": ["src", "controls", "preload", "poster", "width", "height"],
    "audio": ["src", "controls", "preload"],
    "source": ["src", "type", "media"],
    "iframe": ["src", "width", "height", "allow", "allowfullscreen", "frameborder", "title", "sandbox"],
    "h1": ["id"], "h2": ["id"], "h3": ["id"], "h4": ["id"], "h5": ["id"], "h6": ["id"],
    "div": ["id"], "span": ["id"], "section": ["id"],
    "th": ["colspan", "rowspan", "align"], "td": ["colspan", "rowspan", "align"],
    "input": ["type", "checked", "disabled"],
}


def sanitize_content_html(html_content: Optional[str]) -> str:
    """对正文 HTML 做统一白名单过滤，阻止脚本、事件属性与危险链接协议。"""
    raw_html = html_content or ""
    if not raw_html:
        return ""
    # bleach 的 strip 只去标签、会留下脚本正文文本，这里先整段删除 script/style
    raw_html = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1\s*>",
        "",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return bleach.clean(
        raw_html,
        tags=CONTENT_ALLOWED_TAGS,
        attributes=CONTENT_ALLOWED_ATTRIBUTES,
        protocols=("http", "https", "mailto"),
        strip=True,
        strip_comments=True,
    )


def strip_empty_paragraphs(html_content: Optional[str]) -> str:
    """移除富文本编辑器写入的纯空段落，避免前台平白多出一整行空白。

    只处理仅由空白、``<br>`` 或 ``&nbsp;`` 构成的段落；包含图片、文本或
    其他标签的段落一律保留，避免误删正文内容。
    """
    raw_html = html_content or ""
    if not raw_html:
        return ""
    return EMPTY_PARAGRAPH_PATTERN.sub("", raw_html)


def apply_image_size_fragments(html_content: Optional[str]) -> str:
    """把正文图片地址里的尺寸片段转换为真实 class，供前端尺寸样式生效。"""
    raw_html = html_content or ""
    if "#md-img-" not in raw_html:
        return raw_html
    return HTML_IMAGE_TAG_PATTERN.sub(_replace_image_size_fragment, raw_html)


def _html_to_comparable_text(content_html: str) -> str:
    """把 HTML 转成保留段落结构的可比文本，用于快照去重与 diff。"""
    if not content_html:
        return ""

    text = HTML_IMAGE_TAG_PATTERN.sub(lambda match: _image_tag_to_text(match.group(0)), content_html)
    text = HTML_BLOCK_BOUNDARY_PATTERN.sub("\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    lines = [re.sub(r"[ \t\u00a0\u3000]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _render_task_list_items(html_content: str) -> str:
    """把 Markdown 任务列表的 [x] / [ ] 标记渲染为只读复选框。"""
    if "[" not in html_content:
        return html_content

    def replace_item(match: re.Match) -> str:
        checked = " checked" if match.group(1).lower() == "x" else ""
        return f'<li class="task-list-item"><input type="checkbox" class="task-list-checkbox" disabled{checked}> '

    def replace_loose_item(match: re.Match) -> str:
        checked = " checked" if match.group(1).lower() == "x" else ""
        content = (match.group(2) or "").strip()
        return (
            '<li class="task-list-item">'
            f'<input type="checkbox" class="task-list-checkbox" disabled{checked}> {content} '
        )

    html_content = LOOSE_TASK_LIST_ITEM_PATTERN.sub(replace_loose_item, html_content)
    return TASK_LIST_ITEM_PATTERN.sub(replace_item, html_content)


class _StrikethroughExtension(Extension):
    """让 Markdown 模式也支持编辑器的 ~~删除线~~ 语法。"""

    def extendMarkdown(self, md):  # noqa: N802 - Python-Markdown 固定接口名
        md.inlinePatterns.register(
            SimpleTagInlineProcessor(r"(~~)(.+?)~~", "del"),
            "rewrz_strikethrough",
            175,
        )


# Toast UI 会把普通文本里的波浪线转义成 \~，而 Python-Markdown 不消费这个转义；
# 先换成占位符，渲染完再还原成字面量，避免前台把反斜杠显示出来。
_ESCAPED_TILDE_TOKEN = "\x00REWRZ_TILDE\x00"


def _render_plain_markdown(text: str) -> str:
    """渲染不含区块指令的 Markdown 片段。"""
    if not text.strip():
        return ""
    protected = text.replace("\\~", _ESCAPED_TILDE_TOKEN)
    rendered = markdown(
        protected,
        extensions=[*MARKDOWN_RENDER_EXTENSIONS, _StrikethroughExtension()],
    )
    return sanitize_content_html(rendered.replace(_ESCAPED_TILDE_TOKEN, "~"))


def _split_directive_columns(inner: str) -> tuple[str, str, str, bool]:
    """拆分 columns 指令内的 left / right 子块，并保留其余文本。"""
    columns: dict[str, str] = {}
    remainder_parts: list[str] = []
    for kind, payload in _parse_directive_segments(inner):
        if kind == "block" and payload["name"] in {"left", "right"} and payload["name"] not in columns:
            columns[payload["name"]] = payload["inner"]
        elif kind == "text":
            remainder_parts.append(str(payload))
        else:
            # 嵌套的未知块保留内部内容，避免整段被丢弃
            remainder_parts.append(str(payload.get("inner", "")))
    return (
        columns.get("left", ""),
        columns.get("right", ""),
        "".join(remainder_parts),
        bool(columns),
    )


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
        left_inner, right_inner, remainder, has_columns = _split_directive_columns(inner)
        if not has_columns:
            return inner_html
        if remainder.strip():
            # 没有归入 left/right 的内容放进左列，保证不会静默丢失
            left_inner = f"{left_inner}\n\n{remainder}".strip()
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
    fence_char = ""
    fence_length = 0

    while index < len(lines):
        line = lines[index]
        fence_match = FENCE_LINE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not fence_char:
                fence_char = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = ""
                fence_length = 0
            buffer.append(line)
            index += 1
            continue

        # 允许 0-3 个空格缩进（编辑器会 trim 后识别），4 空格仍按代码块处理
        leading_spaces = len(line) - len(line.lstrip(" "))
        match = None
        if not fence_char and leading_spaces < 4:
            match = DIRECTIVE_OPEN_PATTERN.match(line.lstrip(" ").rstrip())
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
        inner_fence_char = ""
        inner_fence_length = 0

        while cursor < len(lines):
            inner_line_raw = lines[cursor]
            inner_fence_match = FENCE_LINE_PATTERN.match(inner_line_raw)
            if inner_fence_match:
                marker = inner_fence_match.group(1)
                if not inner_fence_char:
                    inner_fence_char = marker[0]
                    inner_fence_length = len(marker)
                elif marker[0] == inner_fence_char and len(marker) >= inner_fence_length:
                    inner_fence_char = ""
                    inner_fence_length = 0
            if not inner_fence_char:
                inner_leading = len(inner_line_raw) - len(inner_line_raw.lstrip(" "))
                inner_line = inner_line_raw.strip()
                if inner_leading < 4:
                    if inner_line == DIRECTIVE_CLOSE_LINE:
                        depth -= 1
                        if depth == 0:
                            break
                    elif DIRECTIVE_OPEN_PATTERN.match(inner_line):
                        depth += 1
            inner_lines.append(inner_line_raw)
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

    图片尺寸片段（#md-img-*）在这里统一转成真实 class，保证前台尺寸样式生效。
    """
    return apply_image_size_fragments(_render_markdown_html_cached(content_markdown or ""))


def normalize_content_rating(value: Optional[str], fallback: str = "general") -> str:
    """收敛内容分级取值，未知值回落到给定默认值。"""
    normalized = (value or "").strip().lower()
    if normalized in VALID_CONTENT_RATINGS:
        return normalized
    return fallback if fallback in VALID_CONTENT_RATINGS else "general"


def is_nsfw_rating(value: Optional[str]) -> bool:
    """是否属于需要默认模糊遮挡的分级。"""
    return normalize_content_rating(value) == "nsfw"


def normalize_editor_mode(value: Optional[str], fallback: str = "markdown") -> str:
    mode = (value or "").strip().lower()
    if mode in VALID_EDITOR_MODES:
        return mode
    return fallback if fallback in VALID_EDITOR_MODES else "markdown"


def detect_stored_editor_mode(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    """按存储约定判断已有正文使用的编辑模式。

    存储层面只会保留一种正文：Markdown 模式 content_html 为空，HTML 模式 content_markdown 为空。
    """
    if (content_html or "").strip() and not (content_markdown or "").strip():
        return "html"
    return "markdown"


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
        # HTML 模式同样可能带着编辑器写入的尺寸片段与空段落，这里统一收口
        return sanitize_content_html(strip_empty_paragraphs(apply_image_size_fragments(html_content)))

    return render_markdown_html(content_markdown)


def get_effective_content_html(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    return _get_effective_content_html_cached(content_markdown or "", content_html or "")


@lru_cache(maxsize=128)
def html_to_plain_text(content_html: Optional[str]) -> str:
    raw_html = content_html or ""
    if not raw_html:
        return ""
    # 先剥标签再反解实体，避免 &amp; / &nbsp; 以字面量进入摘要
    plain_text = unescape(re.sub(r"<[^>]+>", " ", raw_html))
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


@lru_cache(maxsize=128)
def _get_comparable_content_text_cached(content_markdown: str, content_html: str) -> str:
    html_content = content_html.strip()
    if html_content:
        text = _html_to_comparable_text(html_content)
        if text:
            return text

    markdown_content = content_markdown.strip()
    if markdown_content:
        rendered_html = render_markdown_html(markdown_content)
        text = _html_to_comparable_text(rendered_html)
        if text:
            return text
        fallback_text = markdown_to_plain_text(markdown_content)
        if fallback_text:
            return fallback_text

    return ""


def get_comparable_content_text(content_markdown: Optional[str], content_html: Optional[str]) -> str:
    """返回保留段落结构的正文可比文本，用于快照去重与差异对比。

    与纯文本口径不同，这里按块级标签断行，Markdown/HTML 两种存储模式
    只要正文一致就会得到相同结果，不会因为编辑器模式切换而产生假差异。
    """
    return _get_comparable_content_text_cached(content_markdown or "", content_html or "")
