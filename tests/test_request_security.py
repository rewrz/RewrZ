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


def _build_request_with_headers(path: str = "/", headers=None, client_host: str = "127.0.0.1") -> Request:
    raw_headers = [(b"accept", b"text/html")]
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode("latin-1"), str(value).encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": raw_headers,
            "client": (client_host, 12345),
            "server": ("example.com", 80),
            "root_path": "",
        }
    )


def test_safe_local_redirect_target_rejects_offsite_and_scheme_relative_urls():
    from rewrz import main as main_module

    assert main_module._safe_local_redirect_target("/posts?page=2") == "/posts?page=2"
    assert main_module._safe_local_redirect_target("") == "/"
    assert main_module._safe_local_redirect_target("//evil.com") == "/"
    assert main_module._safe_local_redirect_target("https://evil.com") == "/"
    assert main_module._safe_local_redirect_target("/\\evil.com") == "/"


def test_allowed_hosts_whitelist_supports_exact_and_subdomain(monkeypatch):
    from rewrz import main as main_module
    from rewrz.core.config import settings

    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["example.com", ".example.org"])

    assert main_module._is_allowed_request_host(
        _build_request_with_headers(headers={"host": "example.com:8080"})
    ) is True
    assert main_module._is_allowed_request_host(
        _build_request_with_headers(headers={"host": "blog.example.org"})
    ) is True
    assert main_module._is_allowed_request_host(
        _build_request_with_headers(headers={"host": "evil.com"})
    ) is False


def test_client_ip_only_trusts_forwarded_for_from_trusted_proxy(monkeypatch):
    from rewrz.core import admin_security
    from rewrz.core.config import settings

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["127.0.0.1"])

    trusted_request = _build_request_with_headers(
        headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"},
        client_host="127.0.0.1",
    )
    assert admin_security.get_client_ip(trusted_request) == "5.6.7.8"

    untrusted_request = _build_request_with_headers(
        headers={"x-forwarded-for": "1.2.3.4"},
        client_host="10.0.0.5",
    )
    assert admin_security.get_client_ip(untrusted_request) == "10.0.0.5"
