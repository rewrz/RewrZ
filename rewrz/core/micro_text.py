import json
import re
from html import escape
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

from bs4 import BeautifulSoup, NavigableString
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..models import User


MICRO_TAG_MAX_LENGTH = 64
MICRO_MENTION_MAX_LENGTH = 32
_MICRO_TOKEN_CHAR_PATTERN = re.compile(r"[0-9A-Za-z_\u4e00-\u9fff-]")
_MICRO_EMAIL_LOCAL_CHAR_PATTERN = re.compile(r"[0-9A-Za-z._%+-]")
_MICRO_EMAIL_DOMAIN_CHAR_PATTERN = re.compile(r"[0-9A-Za-z-]")
_MICRO_ENHANCE_SKIP_PARENTS = {"a", "code", "pre", "script", "style", "textarea"}


def _is_micro_token_char(char: str) -> bool:
    return bool(char) and bool(_MICRO_TOKEN_CHAR_PATTERN.fullmatch(char))


def _is_micro_email_local_char(char: str) -> bool:
    return bool(char) and bool(_MICRO_EMAIL_LOCAL_CHAR_PATTERN.fullmatch(char))


def _looks_like_email_context(source: str, marker_index: int, token_end: int) -> bool:
    if marker_index <= 0:
        return False

    previous_char = source[marker_index - 1]
    if not _is_micro_email_local_char(previous_char):
        return False

    if token_end >= len(source) or source[token_end] != ".":
        return False

    cursor = token_end + 1
    domain_length = 0
    while cursor < len(source) and _MICRO_EMAIL_DOMAIN_CHAR_PATTERN.fullmatch(source[cursor]):
        cursor += 1
        domain_length += 1
    return domain_length > 0


def _iter_micro_token_spans(
    content: str,
    *,
    marker: str,
    max_length: int,
    allow_closing_marker: bool = False,
    email_guard: bool = False,
) -> Iterator[Tuple[int, int, str]]:
    source = str(content or "")
    if not source:
        return

    index = 0
    source_length = len(source)
    while index < source_length:
        if source[index] != marker:
            index += 1
            continue

        if index > 0 and source[index - 1] == marker:
            index += 1
            continue

        cursor = index + 1
        token_chars: List[str] = []
        while cursor < source_length and _is_micro_token_char(source[cursor]):
            token_chars.append(source[cursor])
            cursor += 1

        if not token_chars:
            index += 1
            continue

        token_text = "".join(token_chars)
        span_end = cursor
        if allow_closing_marker and cursor < source_length and source[cursor] == marker:
            span_end = cursor + 1

        if len(token_text) <= max_length:
            if email_guard and _looks_like_email_context(source, index, cursor):
                index = span_end
                continue
            yield index, span_end, token_text

        index = span_end


def extract_micro_tags(content: str, limit: int = 8) -> List[str]:
    tags: List[str] = []
    for _, _, token_text in _iter_micro_token_spans(
        content,
        marker="#",
        max_length=MICRO_TAG_MAX_LENGTH,
        allow_closing_marker=True,
    ):
        raw = token_text.strip().strip("-_")
        if not raw or raw in tags:
            continue
        tags.append(raw)
        if len(tags) >= limit:
            break
    return tags


def strip_micro_tags(content: str) -> str:
    if not content:
        return ""

    stripped_lines: List[str] = []
    for raw_line in str(content).splitlines():
        cleaned_parts: List[str] = []
        cursor = 0
        for start, end, _ in _iter_micro_token_spans(
            raw_line,
            marker="#",
            max_length=MICRO_TAG_MAX_LENGTH,
            allow_closing_marker=True,
        ):
            cleaned_parts.append(raw_line[cursor:start])
            cursor = end
        cleaned_parts.append(raw_line[cursor:])
        cleaned_line = "".join(cleaned_parts)
        cleaned_line = re.sub(r"[ \t]{2,}", " ", cleaned_line).strip()
        stripped_lines.append(cleaned_line)

    stripped_content = "\n".join(stripped_lines)
    stripped_content = re.sub(r"\n{3,}", "\n\n", stripped_content).strip()
    return stripped_content


def _normalize_external_link(raw_link: str) -> str:
    value = str(raw_link or "").strip()
    if not value:
        return ""
    if value.startswith("/"):
        return value
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def load_micro_mention_link_map(db: Optional[Session]) -> Dict[str, str]:
    if db is None:
        return {}

    setting = crud_setting.get_setting(db, "micro_mention_links_json")
    if setting is None or not isinstance(setting.value, dict):
        return {}

    raw_value = setting.value.get("value")
    if raw_value is None:
        return {}

    try:
        parsed = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (TypeError, json.JSONDecodeError):
        return {}

    if isinstance(parsed, list):
        converted: Dict[str, str] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            key_candidate = str(item.get("name", "") or item.get("key", "")).strip()
            link_candidate = str(item.get("url", "") or item.get("link", "")).strip()
            if key_candidate and link_candidate:
                converted[key_candidate] = link_candidate
        parsed = converted

    if not isinstance(parsed, dict):
        return {}

    result: Dict[str, str] = {}
    for raw_name, raw_link in parsed.items():
        name = str(raw_name or "").strip().lstrip("@").lower()
        if not name:
            continue
        safe_link = _normalize_external_link(str(raw_link or ""))
        if not safe_link:
            continue
        result[name] = safe_link
    return result


def resolve_micro_mention_href(
    db: Optional[Session],
    mention_name: str,
    custom_map: Optional[Dict[str, str]] = None,
) -> str:
    normalized_name = str(mention_name or "").strip().lstrip("@")
    if not normalized_name:
        return ""

    mention_map = custom_map or {}
    mapped_href = mention_map.get(normalized_name.lower(), "")
    if mapped_href:
        return mapped_href

    if db is not None:
        matched_user = crud_user.get_user_by_username(db, normalized_name)
        if matched_user is None:
            matched_user = crud_user.get_user_by_username(db, normalized_name.lower())
        if matched_user is None:
            matched_user = db.execute(
                select(User).where(User.display_name == normalized_name)
            ).scalar_one_or_none()
        if matched_user is not None:
            resolved_username = str(getattr(matched_user, "username", "") or "").strip()
            if resolved_username:
                return f"/authors/{quote(resolved_username)}"

    return ""


def _render_micro_inline_text(
    text: str,
    *,
    db: Optional[Session],
    mention_link_map: Dict[str, str],
) -> Tuple[str, bool]:
    source = str(text or "")
    if not source or "@" not in source:
        return escape(source), False

    parts: List[str] = []
    cursor = 0
    changed = False

    for start, end, token_text in _iter_micro_token_spans(
        source,
        marker="@",
        max_length=MICRO_MENTION_MAX_LENGTH,
        email_guard=True,
    ):
        raw_name = token_text.strip()

        parts.append(escape(source[cursor:start]))
        cursor = end

        mention_href = resolve_micro_mention_href(db, raw_name, mention_link_map)
        if mention_href:
            parts.append(
                f'<a href="{escape(mention_href, quote=True)}" class="micro-mention-link">@{escape(raw_name)}</a>'
            )
            changed = True
            continue

        parts.append(escape(source[start:end]))

    parts.append(escape(source[cursor:]))
    return "".join(parts), changed


def enhance_micro_html(content_html: str, db: Optional[Session] = None) -> str:
    if not content_html or "@" not in content_html:
        return content_html

    try:
        soup = BeautifulSoup(content_html, "html.parser")
        mention_link_map = load_micro_mention_link_map(db)

        text_nodes = [
            node
            for node in soup.find_all(string=True)
            if node.parent is not None
            and node.parent.name not in _MICRO_ENHANCE_SKIP_PARENTS
        ]

        for text_node in text_nodes:
            rendered_html, changed = _render_micro_inline_text(
                str(text_node),
                db=db,
                mention_link_map=mention_link_map,
            )
            if not changed:
                continue
            fragment = BeautifulSoup(rendered_html, "html.parser")
            replacement_nodes = list(fragment.contents)
            if replacement_nodes:
                text_node.replace_with(*replacement_nodes)
            else:
                text_node.replace_with(NavigableString(str(text_node)))

        for anchor_node in soup.find_all("a", href=True):
            if anchor_node.get("class") and "micro-mention-link" in anchor_node.get("class", []):
                continue
            previous_sibling = anchor_node.previous_sibling
            if not isinstance(previous_sibling, NavigableString):
                continue
            previous_text = str(previous_sibling)
            if not previous_text.endswith("@"):
                continue

            trimmed_prefix = previous_text[:-1]
            previous_sibling.replace_with(NavigableString(trimmed_prefix))
            anchor_classes = list(anchor_node.get("class", []))
            if "micro-mention-link" not in anchor_classes:
                anchor_classes.append("micro-mention-link")
            anchor_node["class"] = anchor_classes
            anchor_node.string = f"@{anchor_node.get_text(strip=True)}"

        return str(soup)
    except Exception:
        return content_html
