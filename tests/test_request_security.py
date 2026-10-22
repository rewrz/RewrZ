import json
import logging

from starlette.requests import Request

from rewrz.core.database import get_db
from rewrz.core.error_handler import _should_return_json_error, build_database_unavailable_response
from rewrz.core.request_context import (
    REQUEST_ID_HEADER,
    AccessLogRedactionFilter,
    ensure_request_id,
    redact_url_for_log,
)
from rewrz.core.security import get_password_hash, verify_password


def _build_request(path: str, *, accept: str = "text/html") -> Request:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [(b"accept", accept.encode("utf-8"))],
            "client": ("127.0.0.1", 12345),
            "server": ("example.com", 443),
            "root_path": "",
        }
    )
    request.state.admin_path = "/rewrz-admin"
    return request


def test_password_hash_supports_bcrypt_and_72_byte_limit():
    hashed = get_password_hash("正确密码" * 20)

    assert hashed.startswith("$2")
    assert verify_password("正确密码" * 20, hashed) is True
    assert verify_password("错误密码", hashed) is False


def test_get_db_reuses_request_scoped_session():
    closed = {"value": False}

    class DummySession:
        def close(self):
            closed["value"] = True

    shared_session = DummySession()
    request = _build_request("/")
    request.state.db = shared_session

    db_generator = get_db(request)
    assert next(db_generator) is shared_session
    db_generator.close()

    assert closed["value"] is False


def test_redact_url_for_log_hides_admin_path_and_sensitive_query():
    redacted = redact_url_for_log(
        "https://example.com/rewrz-admin/posts?token=abc&page=2&csrf_token=xyz&q=ok",
        "/rewrz-admin",
    )

    assert "/<admin>/posts" in redacted
    assert "rewrz-admin" not in redacted
    assert "token=***" in redacted
    assert "csrf_token=***" in redacted
    assert "page=2" in redacted
    assert "q=ok" in redacted


def test_redact_url_for_log_hides_percent_encoded_admin_path():
    redacted = redact_url_for_log("https://example.com/%72ewrz-admin/posts", "/rewrz-admin")

    assert "/<admin>/posts" in redacted
    assert "rewrz-admin" not in redacted


def test_access_log_filter_redacts_request_target():
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1", "GET", "/rewrz-admin/posts?token=abc", "1.1", 200),
        exc_info=None,
    )

    AccessLogRedactionFilter().filter(record)

    assert record.args[2] == "/<admin>/posts?token=***"


def test_admin_login_errors_return_json_and_request_id():
    request = _build_request("/rewrz-admin/auth", accept="text/html")
    request_id = ensure_request_id(request)

    assert _should_return_json_error(request, "text/html") is True

    response = build_database_unavailable_response(request)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "3"
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert payload["error"]["code"] == "DATABASE_POOL_TIMEOUT"
    assert payload["error"]["request_id"] == request_id
