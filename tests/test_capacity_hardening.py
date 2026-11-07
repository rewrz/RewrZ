"""高流量与拦截加固的回归测试。

覆盖：协议入口豁免、拦截量可观测、高频误判、列表缓存键归一化、
缓存命中不建会话、导航轻量查询、索引与真实 IP 口径。
"""
import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from rewrz import main as main_module
from rewrz.core import public_list_cache, request_guard, time_utils, traffic_analytics
from rewrz.core.database import Base, get_db
from rewrz.core.security import get_client_ip
from rewrz.core.traffic_classifier import classify_request
from rewrz.crud import post as crud_post
from rewrz.crud import traffic as crud_traffic
from rewrz.models import Post, User as DbUser


def _make_request(query: bytes = b"", headers: list | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": query,
            "headers": headers or [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("203.0.113.9", 12345),
        }
    )


@pytest.fixture
def capacity_client(monkeypatch, tmp_path):
    """带独立数据库的公开站点客户端。"""
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    db_path = tmp_path / f"capacity-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with session_local() as db:
        db.add(
            DbUser(
                id=1,
                username="capacity-admin",
                hashed_password="hashed",
                email="capacity@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
            )
        )
        db.commit()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(main_module.app)
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_protocol_paths_are_exempt_from_ua_block():
    assert request_guard.is_blocked_user_agent("AhrefsBot") is True
    assert request_guard.is_blocked_user_agent("SemrushBot") is True
    assert request_guard.is_ua_block_exempt_path("/robots.txt") is True
    # 站点地图含全站 URL 清单，声明文件与订阅入口都不对黑名单 UA 放行
    assert request_guard.is_ua_block_exempt_path("/sitemap.xml") is False
    assert request_guard.is_ua_block_exempt_path("/sitemap_index.xml") is False
    assert request_guard.is_ua_block_exempt_path("/ads.txt") is False
    assert request_guard.is_ua_block_exempt_path("/feed") is False
    assert request_guard.is_ua_block_exempt_path("/") is False
    assert request_guard.is_scanner_path("/robots.txt") is False


@pytest.mark.asyncio
async def test_bot_block_allows_robots_and_records_guard_dimension():
    traffic_analytics.reset_for_tests()

    async def downstream(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = request_guard.BotBlockMiddleware(downstream)

    async def call(path: str, user_agent: bytes) -> list:
        messages = []

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "path": path,
            "scheme": "http",
            "headers": [(b"user-agent", user_agent)],
        }
        await middleware(scope, lambda: None, send)
        return messages

    robots = await call("/robots.txt", b"AhrefsBot")
    assert robots[0]["status"] == 200

    sitemap = await call("/sitemap.xml", b"AhrefsBot/7.0")
    assert sitemap[0]["status"] == 403

    blocked = await call("/some-page", b"AhrefsBot/7.0")
    assert blocked[0]["status"] == 403
    assert blocked[1]["body"] == "禁止访问".encode("utf-8")

    scanner = await call("/wp-admin/setup-config.php", b"Mozilla/5.0")
    assert scanner[0]["status"] == 404

    day = time_utils.site_day_start_utc(time_utils.utc_now_naive())
    guard = traffic_analytics._DIMENSION_VALUES[day]["guard"]
    assert guard["UA 拦截 403"] == 2
    assert guard["扫描路径 404"] == 1


def test_robots_txt_is_readable_by_blocked_bots(capacity_client):
    response = capacity_client.get("/robots.txt", headers={"User-Agent": "AhrefsBot"})
    assert response.status_code == 200
    assert "User-agent" in response.text

    sitemap = capacity_client.get("/sitemap.xml", headers={"User-Agent": "AhrefsBot"})
    assert sitemap.status_code == 403


def test_idempotent_api_has_relaxed_frequency_threshold():
    api_result = classify_request(
        path="/api/v1/reactions/summary",
        method="GET",
        status_code=200,
        requests_in_minute=100,
    )
    assert "高频访问" not in api_result.suspicious_reason

    page_result = classify_request(
        path="/",
        method="GET",
        status_code=200,
        content_type="text/html",
        requests_in_minute=61,
    )
    assert "高频访问" in page_result.suspicious_reason


def test_list_cache_key_ignores_unrelated_query_parameters():
    key_a = public_list_cache._build_cache_key(
        _make_request(b"p=123&utm_source=weibo"), 1
    )
    key_b = public_list_cache._build_cache_key(_make_request(b"p=999"), 1)
    key_c = public_list_cache._build_cache_key(_make_request(b"page=2"), 1)
    assert key_a == key_b
    assert key_a != key_c


def test_logged_in_cookie_bypasses_public_list_cache():
    request = _make_request(headers=[(b"cookie", b"access_token=fake-token")])
    assert public_list_cache.is_cacheable_public_list_request(request) is False


def test_list_cache_hit_skips_request_session_and_ignores_p_query(
    capacity_client, monkeypatch
):
    first = capacity_client.get("/")
    assert first.status_code == 200

    calls = []
    original = main_module._prepare_request_state

    def counting(request):
        calls.append(request.url.path)
        return original(request)

    monkeypatch.setattr(main_module, "_prepare_request_state", counting)

    second = capacity_client.get("/")
    assert second.status_code == 200
    assert "s-maxage=20" in second.headers.get("cache-control", "")
    assert calls == []

    legacy_probe = capacity_client.get("/?p=123456")
    assert legacy_probe.status_code == 200
    assert calls == []


def test_nav_pages_are_lightweight_cached_and_invalidatable(test_db, monkeypatch):
    published_at = datetime(2026, 1, 1, 8, 0, 0)
    test_db.add(
        Post(
            title="关于本站",
            slug="about",
            content_markdown="页面正文",
            content_html="<p>页面正文</p>",
            post_type="page",
            status="published",
            visibility="public",
            published_at=published_at,
        )
    )
    test_db.add(
        Post(
            title="普通文章",
            slug="normal-post",
            content_markdown="文章正文",
            content_html="<p>文章正文</p>",
            post_type="post",
            status="published",
            visibility="public",
            published_at=published_at,
        )
    )
    test_db.commit()

    original_execute = test_db.execute
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(test_db, "execute", counting)

    first = crud_post.get_public_nav_pages(test_db)
    second = crud_post.get_public_nav_pages(test_db)
    assert [item["slug"] for item in first] == ["about"]
    assert set(first[0]) == {"slug", "title"}
    assert second == first
    assert len(calls) == 1

    crud_post.invalidate_nav_pages_cache()
    crud_post.get_public_nav_pages(test_db)
    assert len(calls) == 2


def test_posts_table_has_listing_indexes(test_engine):
    names = {item["name"] for item in inspect(test_engine).get_indexes("posts")}
    assert "ix_posts_public_listing" in names
    assert "ix_posts_page_nav" in names


def test_analytics_summary_exposes_guard_dimension(test_db):
    summary = crud_traffic.get_analytics_summary(test_db, "today")
    assert summary["guard_blocks"] == []


def test_client_ip_ignores_spoofed_forwarded_header():
    request = _make_request(headers=[(b"x-forwarded-for", b"1.2.3.4")])
    assert get_client_ip(request) == "203.0.113.9"


def test_akismet_check_sets_total_timeout(monkeypatch):
    from rewrz.core import akismet_client

    captured = []

    class FakeResponse:
        headers = {}

        async def text(self):
            return "false"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def __init__(self, timeout=None):
            captured.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data=None):
            return FakeResponse()

    monkeypatch.setattr(akismet_client.aiohttp, "ClientSession", FakeSession)
    client = akismet_client.AkismetClient("test-key", "https://example.com")
    result = asyncio.run(client.check_comment("评论正文"))
    assert result["is_spam"] is False
    assert captured and captured[0].total == akismet_client.COMMENT_CHECK_TIMEOUT_SECONDS

    # 密钥验证是低频后台操作，等待上限必须比评论检查宽松，避免有效密钥被误判
    assert asyncio.run(client.verify_key()) is False
    assert captured[-1].total == akismet_client.BACKGROUND_TIMEOUT_SECONDS
    assert (
        akismet_client.BACKGROUND_TIMEOUT_SECONDS
        > akismet_client.COMMENT_CHECK_TIMEOUT_SECONDS
    )
