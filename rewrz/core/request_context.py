"""请求上下文辅助：请求 ID 与日志脱敏。"""

from __future__ import annotations

import logging
import re
import uuid
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from .admin_path import get_admin_path, normalize_admin_path


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "signature",
    "credential",
)
_MAX_LOGGED_URL_LENGTH = 2000


def normalize_request_id(raw_value) -> str:
    """校验外部传入的请求 ID，非法值直接丢弃。"""
    value = str(raw_value or "").strip()
    if not value or not _REQUEST_ID_PATTERN.fullmatch(value):
        return ""
    return value


def ensure_request_id(request) -> str:
    """为请求生成或复用安全格式的请求 ID。"""
    request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    if not request_id:
        request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    return request_id


def get_request_id(request) -> str:
    """读取当前请求 ID，缺失时补生成。"""
    if request is None:
        return ""
    value = normalize_request_id(getattr(request.state, "request_id", ""))
    if value:
        return value
    return ensure_request_id(request)


def _is_sensitive_query_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_url_for_log(raw_url: str, admin_path: str | None = None) -> str:
    """脱敏 URL 中的后台路径和敏感查询参数。"""
    raw_text = str(raw_url or "")
    if not raw_text:
        return ""

    try:
        parsed = urlsplit(raw_text)
    except ValueError:
        return raw_text[:_MAX_LOGGED_URL_LENGTH]

    path = parsed.path or ""
    decoded_path = unquote(path)
    normalized_admin_path = normalize_admin_path(admin_path or get_admin_path())
    if normalized_admin_path != "/":
        if decoded_path == normalized_admin_path:
            path = "/<admin>"
        elif decoded_path.startswith(f"{normalized_admin_path}/"):
            path = f"/<admin>{decoded_path[len(normalized_admin_path):]}"

    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"<redacted>@{netloc.rsplit('@', 1)[-1]}"

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query_items.append((key, "***" if _is_sensitive_query_key(key) else value))

    redacted = urlunsplit((
        parsed.scheme,
        netloc,
        path,
        urlencode(query_items, doseq=True, safe="*"),
        parsed.fragment,
    ))
    return redacted[:_MAX_LOGGED_URL_LENGTH]


class AccessLogRedactionFilter(logging.Filter):
    """脱敏 uvicorn access log 中的后台路径和敏感参数。"""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            sanitized_args = list(args)
            sanitized_args[2] = redact_url_for_log(sanitized_args[2])
            record.args = tuple(sanitized_args)
        return True


def install_access_log_redaction_filter() -> None:
    """幂等安装 uvicorn 访问日志脱敏过滤器。"""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, AccessLogRedactionFilter) for item in access_logger.filters):
        access_logger.addFilter(AccessLogRedactionFilter())
