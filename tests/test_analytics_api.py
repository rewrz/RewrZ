"""访问统计后台 API 与页面测试。"""
from __future__ import annotations

import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.api import analytics as analytics_api
from rewrz.core import traffic_analytics
from rewrz.core.config import settings as app_settings
from rewrz.core.database import Base, get_db
from rewrz.core.security import get_current_user
from rewrz.core.time_utils import site_day_start_utc
from rewrz.models import (
    TrafficDimensionDaily,
    TrafficHourStat,
    TrafficVisitorDaily,
)
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser


@pytest.fixture
def traffic_db(tmp_path):
    """每个测试使用独立数据库，避免统计聚合数据跨用例串扰。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'traffic-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _ensure_admin_routes_registered() -> None:
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True


def _seed_admin_basics(db) -> DbUser:
    user = db.query(DbUser).filter(DbUser.id == 1).first()
    if user is None:
        user = DbUser(
            id=1,
            username="admin",
            hashed_password="hashed",
            email="admin@example.com",
            is_active=True,
            role="super_admin",
            use_gravatar="auto",
            display_name="管理员",
        )
        db.add(user)

    existing_keys = {item.key for item in db.query(Setting).all()}
    default_settings = {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "https://example.com"},
        "smtp_port": {"value": 587},
    }
    for key, value in default_settings.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))

    db.commit()
    db.refresh(user)
    return user


def _login_user_override() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )


def _build_admin_client(traffic_db, monkeypatch) -> TestClient:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    _seed_admin_basics(traffic_db)
    main_module.app.dependency_overrides[get_db] = lambda: traffic_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app)


def _extract_csrf_token(response_text: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response_text)
    assert match is not None, "页面中未找到 CSRF 令牌"
    return match.group(1)


def _insert_today_stats(
    traffic_db,
    *,
    requests: int = 10,
    page_views: int = 6,
    beacon_page_views: int = 0,
) -> None:
    day_start = site_day_start_utc()
    traffic_db.add(
        TrafficHourStat(
            bucket_start=day_start,
            requests=requests,
            page_views=page_views,
            beacon_page_views=beacon_page_views,
            bot_requests=2,
            suspicious_requests=1,
            status_4xx=1,
            status_5xx=0,
        )
    )
    dimension_rows = (
        ("path", "/hello", 5),
        ("referer", "www.google.com", 3),
        ("source_type", "search", 3),
        ("source_type", "direct", 2),
        ("bot", "Googlebot", 2),
        ("status", "200", 8),
        ("utm_source", "newsletter", 2),
    )
    for kind, value, hits in dimension_rows:
        traffic_db.add(
            TrafficDimensionDaily(
                day_start_utc=day_start, kind=kind, value=value, hits=hits
            )
        )
    traffic_db.add(
        TrafficVisitorDaily(day_start_utc=day_start, visitor_hash="a" * 32, hits=1)
    )
    traffic_db.add(
        TrafficVisitorDaily(day_start_utc=day_start, visitor_hash="b" * 32, hits=1)
    )
    traffic_db.commit()


def test_analytics_page_requires_login(traffic_db, monkeypatch):
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    _seed_admin_basics(traffic_db)
    main_module.app.dependency_overrides[get_db] = lambda: traffic_db
    client = TestClient(main_module.app)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        response = client.get(f"{admin_prefix}/analytics", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"{admin_prefix}/login"
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_page_empty_state_and_all_ranges(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page = client.get(f"{admin_prefix}/analytics")
        assert page.status_code == 200
        assert page.headers.get("cache-control") == "private, no-store"
        assert "访问趋势" in page.text
        assert "暂无路径数据" in page.text

        for range_key in ("today", "week", "month", "year", "recent_years"):
            response = client.get(
                f"{admin_prefix}/api/v1/analytics/summary?range={range_key}"
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["range"]["key"] == range_key
            assert payload["totals"]["requests"] == 0
            assert payload["notes"]
            assert response.headers.get("cache-control") == "private, no-store"

        custom = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=custom&start=2026-01-01&end=2026-01-31"
        )
        assert custom.status_code == 200
        assert custom.json()["range"]["key"] == "custom"

        missing = client.get(f"{admin_prefix}/api/v1/analytics/summary?range=custom")
        assert missing.status_code == 400

        invalid = client.get(f"{admin_prefix}/api/v1/analytics/summary?range=unknown")
        assert invalid.status_code == 400
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_summary_aggregates_totals_dimensions_and_uv(traffic_db, monkeypatch):
    _insert_today_stats(traffic_db)
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        response = client.get(f"{admin_prefix}/api/v1/analytics/summary?range=today")
        assert response.status_code == 200
        payload = response.json()

        assert payload["totals"]["requests"] == 10
        assert payload["totals"]["page_views"] == 6
        assert payload["totals"]["beacon_page_views"] == 0
        # 没有前端上报时，有效访问回退为回源页面访问
        assert payload["totals"]["effective_page_views"] == 6
        assert payload["totals"]["bot_requests"] == 2
        assert payload["totals"]["suspicious_requests"] == 1
        assert payload["totals"]["uv"] == 2
        assert payload["compare"]["requests"] is None
        assert payload["paths"][0]["value"] == "/hello"
        assert any(item["label"] == "搜索引擎" for item in payload["source_types"])
        assert payload["bots"][0]["value"] == "Googlebot"
        assert payload["utm_sources"][0]["value"] == "newsletter"
        assert payload["capacity"]["metrics"]["dialect"] == "sqlite"
        assert payload["trend"]
        assert payload["uv_coverage_days"] == 1
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_summary_prefers_beacon_page_views(traffic_db, monkeypatch):
    _insert_today_stats(traffic_db, requests=10, page_views=6, beacon_page_views=14)
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        payload = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today"
        ).json()
        assert payload["totals"]["page_views"] == 6
        assert payload["totals"]["beacon_page_views"] == 14
        assert payload["totals"]["effective_page_views"] == 14

        point = payload["trend"][0]
        assert point["page_views"] == 6
        assert point["beacon_page_views"] == 14
        assert point["effective_page_views"] == 14
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_dimensions_follow_beacon_when_reporting_dominates(traffic_db, monkeypatch):
    _insert_today_stats(traffic_db, requests=10, page_views=6, beacon_page_views=14)
    day_start = site_day_start_utc()
    traffic_db.add(
        TrafficDimensionDaily(
            day_start_utc=day_start, kind="beacon_path", value="/cached", hits=14
        )
    )
    traffic_db.add(
        TrafficDimensionDaily(
            day_start_utc=day_start, kind="beacon_source_type", value="search", hits=14
        )
    )
    traffic_db.commit()
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        payload = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today"
        ).json()
        assert payload["totals"]["effective_page_views"] == 14
        assert payload["paths"][0]["value"] == "/cached"
        assert payload["paths"][0]["hits"] == 14
        assert payload["source_types"][0]["label"] == "搜索引擎"
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_effective_page_views_keeps_larger_origin_value(traffic_db, monkeypatch):
    # 上报被拦截或只有少量 JS 用户时，回源 PV 更大，不应被少量上报拉低
    _insert_today_stats(traffic_db, requests=30, page_views=20, beacon_page_views=3)
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        payload = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today"
        ).json()
        assert payload["totals"]["effective_page_views"] == 20
        # 回源维度更完整，仍使用回源维度
        assert payload["paths"][0]["value"] == "/hello"
        assert payload["trend"][0]["effective_page_views"] == 20
    finally:
        main_module.app.dependency_overrides.clear()


def test_beacon_endpoint_records_page_view_without_double_counting(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    traffic_analytics.reset_for_tests()

    def _post(payload, headers=None, path="/api/v1/traffic/pageview"):
        return client.post(path, json=payload, headers=headers or {})

    try:
        response = _post(
            {"path": "/posts/hello", "referrer": "https://www.google.com/", "query": ""},
            headers={"sec-fetch-site": "same-origin", "origin": "http://testserver"},
        )
        assert response.status_code == 204
        assert response.headers["cache-control"] == "no-store"
        bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
        assert bucket["beacon_page_views"] == 1
        # 中间件必须跳过 beacon 路径，否则会把上报重复计入回源请求数
        assert bucket["requests"] == 0
        assert bucket["page_views"] == 0

        # 跨站来源、超长请求体、非法 JSON、后台路径与爬虫 UA 一律忽略
        _post(
            {"path": "/posts/hello"},
            headers={"sec-fetch-site": "cross-site", "origin": "https://evil.example"},
        )
        _post({"path": "/" + "x" * 3000})
        client.post(
            "/api/v1/traffic/pageview",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        _post({"path": f"{app_settings.ADMIN_PATH.rstrip('/')}/dashboard"})
        _post({"path": "/posts/hello"}, headers={"user-agent": "Googlebot/2.1"})

        bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
        assert bucket["beacon_page_views"] == 1
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_summary_cache_and_refresh(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        first = client.get(f"{admin_prefix}/api/v1/analytics/summary?range=today")
        assert first.status_code == 200
        assert first.json()["totals"]["requests"] == 0

        _insert_today_stats(traffic_db, requests=7, page_views=4)

        cached = client.get(f"{admin_prefix}/api/v1/analytics/summary?range=today")
        assert cached.json()["totals"]["requests"] == 0

        refreshed = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today&refresh=1"
        )
        assert refreshed.json()["totals"]["requests"] == 7
        assert refreshed.json()["totals"]["page_views"] == 4
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_today_boundary_ignores_previous_site_day(traffic_db, monkeypatch):
    day_start = site_day_start_utc()
    traffic_db.add(TrafficHourStat(bucket_start=day_start - timedelta(hours=1), requests=99))
    traffic_db.add(TrafficHourStat(bucket_start=day_start, requests=4))
    traffic_db.commit()

    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        payload = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today"
        ).json()
        assert payload["totals"]["requests"] == 4
    finally:
        main_module.app.dependency_overrides.clear()


def test_dashboard_traffic_summary_empty_then_populated(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        empty = client.get(f"{admin_prefix}/api/v1/dashboard/traffic-summary")
        assert empty.status_code == 200
        assert "今日有效访问" in empty.text
        assert "暂无可展示的统计数据" in empty.text
        assert empty.headers.get("cache-control") == "private, no-store"

        _insert_today_stats(traffic_db, requests=11, page_views=8)
        analytics_api.clear_caches()

        filled = client.get(f"{admin_prefix}/api/v1/dashboard/traffic-summary")
        assert filled.status_code == 200
        assert "今日总请求" in filled.text
        assert "11" in filled.text
        assert "回源 8 / 上报 0" in filled.text
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_settings_requires_csrf_and_validates_retention(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page = client.get(f"{admin_prefix}/analytics")
        token = _extract_csrf_token(page.text)

        no_csrf = client.post(
            f"{admin_prefix}/analytics/settings",
            data={"enabled": "1", "retention_days": "90"},
        )
        assert no_csrf.status_code == 403

        invalid = client.post(
            f"{admin_prefix}/analytics/settings",
            data={"enabled": "1", "retention_days": "10", "csrf_token": token},
        )
        assert invalid.status_code == 400

        disabled = client.post(
            f"{admin_prefix}/analytics/settings",
            data={"retention_days": "90", "csrf_token": token},
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert "saved=1" in disabled.headers["location"]
        settings = traffic_analytics.get_analytics_settings(traffic_db)
        assert settings["enabled"] is False
        assert settings["retention_days"] == 90
        assert traffic_analytics.is_enabled() is False
    finally:
        main_module.app.dependency_overrides.clear()


def test_analytics_clear_requires_csrf_and_clears_rows(traffic_db, monkeypatch):
    _insert_today_stats(traffic_db)
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        page = client.get(f"{admin_prefix}/analytics")
        token = _extract_csrf_token(page.text)

        no_csrf = client.post(f"{admin_prefix}/analytics/clear")
        assert no_csrf.status_code == 403

        cleared = client.post(
            f"{admin_prefix}/analytics/clear",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert cleared.status_code == 303
        assert "cleared=1" in cleared.headers["location"]

        assert traffic_db.execute(select(TrafficHourStat)).scalars().all() == []
        assert traffic_db.execute(select(TrafficDimensionDaily)).scalars().all() == []
        assert traffic_db.execute(select(TrafficVisitorDaily)).scalars().all() == []

        token_setting = (
            traffic_db.query(Setting)
            .filter(Setting.key == traffic_analytics.TRAFFIC_RESET_TOKEN_KEY)
            .one()
        )
        assert token_setting.value["value"]

        refreshed = client.get(
            f"{admin_prefix}/api/v1/analytics/summary?range=today&refresh=1"
        )
        assert refreshed.json()["totals"]["requests"] == 0
    finally:
        main_module.app.dependency_overrides.clear()


def test_static_assets_are_not_recorded_by_middleware(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        traffic_analytics.reset_for_tests()
        static_response = client.get("/static/favicon.ico")
        assert static_response.status_code == 200
        assert traffic_analytics._MINUTE_BUCKETS == {}
        assert traffic_analytics._HOUR_BUCKETS == {}

        page = client.get(f"{admin_prefix}/analytics")
        assert page.status_code == 200
        assert traffic_analytics._MINUTE_BUCKETS
        assert traffic_analytics._HOUR_BUCKETS
    finally:
        main_module.app.dependency_overrides.clear()


def test_live_fragment_and_dashboard_widget_links(traffic_db, monkeypatch):
    client = _build_admin_client(traffic_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")

    try:
        live = client.get(f"{admin_prefix}/api/v1/analytics/live")
        assert live.status_code == 200
        assert "最近 60 分钟" in live.text or "流量平稳" in live.text
        assert live.headers.get("cache-control") == "private, no-store"

        dashboard = client.get(f"{admin_prefix}/dashboard")
        assert dashboard.status_code == 200
        assert f"{admin_prefix}/analytics" in dashboard.text
        assert "访问统计" in dashboard.text
    finally:
        main_module.app.dependency_overrides.clear()
