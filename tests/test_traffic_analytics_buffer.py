"""访问统计缓冲、刷写、清理与设置测试。"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import sessionmaker

from rewrz.core import traffic_analytics
from rewrz.core.admin_path import get_admin_path
from rewrz.core.database import Base
from rewrz.core.time_utils import site_day_start_utc, utc_now_naive
from rewrz.crud import traffic as crud_traffic
from rewrz.models import (
    TrafficAnomalySource,
    TrafficDimensionDaily,
    TrafficHourStat,
    TrafficMinuteStat,
    TrafficVisitorDaily,
)
from rewrz.models.setting import Setting


@pytest.fixture
def traffic_db(tmp_path):
    """每个测试使用独立数据库，避免统计聚合数据跨用例串扰。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'traffic-buffer.db'}",
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


def _fake_request(path: str = "/", method: str = "GET", query: str = "", referer: str = ""):
    headers = {"host": "example.com", "user-agent": "Mozilla/5.0"}
    if referer:
        headers["referer"] = referer
    return SimpleNamespace(
        headers=headers,
        url=SimpleNamespace(path=path, query=query),
        method=method,
        state=SimpleNamespace(authenticated_user=None),
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _html_response(status_code: int = 200):
    return SimpleNamespace(
        status_code=status_code,
        headers={"content-type": "text/html; charset=utf-8"},
    )


def _make_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_record_request_updates_buffers_and_flush_persists(traffic_db, monkeypatch):
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    request = _fake_request(path="/posts/hello", referer="https://www.google.com/search?q=rewrz")
    response = _html_response()
    traffic_analytics.record_http_request(request, response, None)
    traffic_analytics.record_http_request(request, response, None)

    minute_bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
    assert minute_bucket["requests"] == 2
    assert minute_bucket["page_views"] == 2

    traffic_analytics._flush_once()

    assert traffic_analytics._MINUTE_BUCKETS == {}
    assert traffic_analytics._LAST_FLUSH_ERROR == ""

    traffic_db.expire_all()
    minute_row = traffic_db.execute(select(TrafficMinuteStat)).scalars().one()
    assert minute_row.requests == 2
    assert minute_row.page_views == 2
    hour_row = traffic_db.execute(select(TrafficHourStat)).scalars().one()
    assert hour_row.requests == 2

    dimensions = {
        (row.kind, row.value): row.hits
        for row in traffic_db.execute(select(TrafficDimensionDaily)).scalars().all()
    }
    assert dimensions[("path", "/posts/hello")] == 2
    assert dimensions[("referer", "www.google.com")] == 2
    assert dimensions[("source_type", "search")] == 2
    assert dimensions[("status", "200")] == 2

    visitors = traffic_db.execute(select(TrafficVisitorDaily)).scalars().all()
    assert len(visitors) == 1
    assert int(visitors[0].hits) == 2

    # 再记录一次爬虫请求，验证 upsert 是累加而不是覆盖
    bot_request = _fake_request(path="/")
    bot_request.headers["user-agent"] = "Mozilla/5.0 (compatible; Googlebot/2.1)"
    traffic_analytics.record_http_request(bot_request, response, None)
    traffic_analytics._flush_once()

    traffic_db.expire_all()
    hour_row = traffic_db.execute(select(TrafficHourStat)).scalars().one()
    assert int(hour_row.requests) == 3
    assert int(hour_row.page_views) == 2
    assert int(hour_row.bot_requests) == 1
    dimensions = {
        (row.kind, row.value): row.hits
        for row in traffic_db.execute(select(TrafficDimensionDaily)).scalars().all()
    }
    assert dimensions[("bot", "Googlebot")] == 1


def test_flush_failure_restores_buffers(traffic_db, monkeypatch):
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.11")
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    def broken_upsert(*args, **kwargs):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr(traffic_analytics, "_upsert_minute_rows", broken_upsert)

    traffic_analytics.record_http_request(_fake_request(), _html_response(), None)
    traffic_analytics._flush_once()

    assert traffic_analytics._LAST_FLUSH_ERROR
    minute_bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
    assert minute_bucket["requests"] == 1
    assert minute_bucket["page_views"] == 1


def test_apply_runtime_state_discards_buffers_on_reset_token_change(monkeypatch):
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.12")
    traffic_analytics._apply_runtime_state(True, "")
    traffic_analytics.record_http_request(_fake_request(), _html_response(), None)
    assert traffic_analytics._MINUTE_BUCKETS

    traffic_analytics._apply_runtime_state(True, "token-a")
    assert traffic_analytics._MINUTE_BUCKETS

    traffic_analytics._apply_runtime_state(True, "token-b")
    assert traffic_analytics._MINUTE_BUCKETS == {}


def test_analytics_settings_clamp_and_toggle(traffic_db):
    result = traffic_analytics.save_analytics_settings(
        traffic_db, enabled=False, retention_days=10
    )
    assert result == {"enabled": False, "retention_days": 30}
    assert traffic_analytics.is_enabled() is False

    result = traffic_analytics.save_analytics_settings(
        traffic_db, enabled=True, retention_days=1000
    )
    assert result == {"enabled": True, "retention_days": 730}
    assert traffic_analytics.is_enabled() is True

    settings = traffic_analytics.get_analytics_settings(traffic_db)
    assert settings["enabled"] is True
    assert settings["retention_days"] == 730


def test_clear_analytics_data_removes_rows_and_broadcasts_reset_token(traffic_db):
    now = utc_now_naive()
    traffic_db.add(TrafficMinuteStat(bucket_start=now.replace(second=0, microsecond=0), requests=1))
    traffic_db.add(TrafficHourStat(bucket_start=now.replace(minute=0, second=0, microsecond=0), requests=1))
    traffic_db.add(
        TrafficDimensionDaily(
            day_start_utc=site_day_start_utc(now), kind="path", value="/", hits=1
        )
    )
    traffic_db.add(
        TrafficVisitorDaily(
            day_start_utc=site_day_start_utc(now), visitor_hash="a" * 32, hits=1
        )
    )
    traffic_db.add(
        TrafficAnomalySource(
            ip="198.51.100.7",
            hits=1,
            reason="敏感路径",
            sample_path="/.env",
            sample_user_agent="curl/8.0",
            first_seen=now,
            last_seen=now,
        )
    )
    traffic_db.commit()

    traffic_analytics.clear_analytics_data(traffic_db)

    assert traffic_db.execute(select(TrafficMinuteStat)).scalars().all() == []
    assert traffic_db.execute(select(TrafficHourStat)).scalars().all() == []
    assert traffic_db.execute(select(TrafficDimensionDaily)).scalars().all() == []
    assert traffic_db.execute(select(TrafficVisitorDaily)).scalars().all() == []
    assert traffic_db.execute(select(TrafficAnomalySource)).scalars().all() == []

    token_setting = (
        traffic_db.query(Setting)
        .filter(Setting.key == traffic_analytics.TRAFFIC_RESET_TOKEN_KEY)
        .one()
    )
    assert token_setting.value["value"]


def test_cleanup_respects_retention_windows(traffic_db, monkeypatch):
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    now = utc_now_naive()
    minute_now = now.replace(second=0, microsecond=0)
    session = session_factory()
    session.add(TrafficMinuteStat(bucket_start=minute_now - timedelta(hours=49), requests=1))
    session.add(TrafficMinuteStat(bucket_start=minute_now - timedelta(hours=1), requests=1))
    session.add(TrafficHourStat(bucket_start=now - timedelta(days=365 * 3 + 1), requests=1))
    session.add(TrafficHourStat(bucket_start=now - timedelta(days=1), requests=1))
    session.add(
        TrafficDimensionDaily(
            day_start_utc=site_day_start_utc(now - timedelta(days=40)),
            kind="path",
            value="/old",
            hits=1,
        )
    )
    session.add(
        TrafficDimensionDaily(
            day_start_utc=site_day_start_utc(now - timedelta(days=1)),
            kind="path",
            value="/new",
            hits=1,
        )
    )
    session.add(
        TrafficVisitorDaily(
            day_start_utc=site_day_start_utc(now - timedelta(days=40)),
            visitor_hash="b" * 32,
            hits=1,
        )
    )
    session.add(
        TrafficVisitorDaily(
            day_start_utc=site_day_start_utc(now - timedelta(days=1)),
            visitor_hash="c" * 32,
            hits=1,
        )
    )
    session.add(
        TrafficAnomalySource(
            ip="198.51.100.8",
            hits=1,
            reason="测试",
            sample_path="/old",
            sample_user_agent="",
            first_seen=now - timedelta(days=8),
            last_seen=now - timedelta(days=8),
        )
    )
    session.add(
        TrafficAnomalySource(
            ip="198.51.100.9",
            hits=1,
            reason="测试",
            sample_path="/new",
            sample_user_agent="",
            first_seen=now - timedelta(hours=1),
            last_seen=now - timedelta(hours=1),
        )
    )
    session.commit()
    session.close()

    counts = traffic_analytics.cleanup_traffic_data(retention_days=30)
    assert counts["minute_stats"] == 1
    assert counts["hour_stats"] == 1
    assert counts["dimensions"] == 1
    assert counts["visitors"] == 1
    assert counts["anomalies"] == 1

    verify = session_factory()
    minute_starts = {
        row.bucket_start for row in verify.execute(select(TrafficMinuteStat)).scalars().all()
    }
    assert len(minute_starts) == 1
    assert (now - timedelta(hours=1)).replace(second=0, microsecond=0) in minute_starts

    paths = {
        row.value
        for row in verify.execute(
            select(TrafficDimensionDaily).where(TrafficDimensionDaily.kind == "path")
        ).scalars().all()
    }
    assert paths == {"/new"}
    anomaly_ips = {
        row.ip for row in verify.execute(select(TrafficAnomalySource)).scalars().all()
    }
    assert anomaly_ips == {"198.51.100.9"}
    verify.close()

    check = session_factory()
    cleaned = (
        check.query(Setting)
        .filter(Setting.key == traffic_analytics.TRAFFIC_LAST_CLEANED_KEY)
        .one()
    )
    assert cleaned.value["value"]
    check.close()


def test_beacon_page_view_only_counts_beacon_and_flushes(traffic_db, monkeypatch):
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.20")
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    request = _fake_request(path="/posts/hello")
    traffic_analytics.record_beacon_page_view(
        request,
        path="/posts/hello",
        referrer="https://www.google.com/search?q=rewrz",
        # 浏览器 location.search 带前导 "?"，必须能正确解析 UTM
        query_string="?utm_source=newsletter",
    )

    minute_bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
    assert minute_bucket["beacon_page_views"] == 1
    # beacon 只是前端 PV 补充，不得计入回源请求数与回源 PV
    assert minute_bucket["requests"] == 0
    assert minute_bucket["page_views"] == 0

    traffic_analytics._flush_once()

    traffic_db.expire_all()
    minute_row = traffic_db.execute(select(TrafficMinuteStat)).scalars().one()
    assert minute_row.beacon_page_views == 1
    assert minute_row.requests == 0
    assert minute_row.page_views == 0
    hour_row = traffic_db.execute(select(TrafficHourStat)).scalars().one()
    assert hour_row.beacon_page_views == 1
    assert hour_row.requests == 0

    dimensions = {
        (row.kind, row.value): row.hits
        for row in traffic_db.execute(select(TrafficDimensionDaily)).scalars().all()
    }
    # 上报维度独立存放，避免与回源维度相加造成重复计数
    assert dimensions[("beacon_path", "/posts/hello")] == 1
    assert dimensions[("beacon_referer", "www.google.com")] == 1
    assert dimensions[("beacon_source_type", "search")] == 1
    assert dimensions[("beacon_utm_source", "newsletter")] == 1
    assert ("path", "/posts/hello") not in dimensions
    # beacon 不携带响应状态码，不应产生 status 维度
    assert ("status", "200") not in dimensions

    visitors = traffic_db.execute(select(TrafficVisitorDaily)).scalars().all()
    assert len(visitors) == 1


def test_beacon_page_view_rejects_invalid_targets(traffic_db, monkeypatch):
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.21")
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    def _record(path: str, user_agent: str = "Mozilla/5.0"):
        request = _fake_request(path=path)
        request.headers["user-agent"] = user_agent
        traffic_analytics.record_beacon_page_view(
            request, path=path, referrer="", query_string=""
        )

    _record("")
    _record("posts/hello")
    _record("//evil.example/posts/hello")
    _record(f"{get_admin_path()}/dashboard")
    _record("/posts/hello", user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert traffic_analytics._MINUTE_BUCKETS == {}

    _record("/posts/hello")
    assert next(iter(traffic_analytics._MINUTE_BUCKETS.values()))["beacon_page_views"] == 1

    # 开关关闭后不再记录
    monkeypatch.setattr(traffic_analytics, "_ENABLED", False)
    traffic_analytics.reset_buffers()
    _record("/posts/hello")
    assert traffic_analytics._MINUTE_BUCKETS == {}


def test_beacon_page_view_rate_limits_per_ip(monkeypatch):
    fixed_now = datetime(2026, 10, 24, 12, 0, 0)
    monkeypatch.setattr(traffic_analytics.time_utils, "utc_now_naive", lambda: fixed_now)
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.22")

    request = _fake_request(path="/posts/hello")
    for _ in range(traffic_analytics.MAX_BEACON_PER_IP_MINUTE + 20):
        traffic_analytics.record_beacon_page_view(
            request, path="/posts/hello", referrer="", query_string=""
        )

    minute_bucket = traffic_analytics._MINUTE_BUCKETS[fixed_now]
    assert minute_bucket["beacon_page_views"] == traffic_analytics.MAX_BEACON_PER_IP_MINUTE


def test_user_4xx_only_counts_non_bot_non_suspicious_requests(traffic_db, monkeypatch):
    """4xx 指标只反映真实用户请求，扫描器与爬虫不参与比例。"""
    session_factory = _make_session_factory(traffic_db.get_bind())
    monkeypatch.setattr(traffic_analytics, "_get_client_ip", lambda request: "203.0.113.30")
    monkeypatch.setattr(traffic_analytics.db_manager, "get_session", lambda: session_factory())

    traffic_analytics.record_http_request(_fake_request(path="/missing-page"), _html_response(404), None)

    bot_request = _fake_request(path="/missing-page")
    bot_request.headers["user-agent"] = "Mozilla/5.0 (compatible; Googlebot/2.1)"
    traffic_analytics.record_http_request(bot_request, _html_response(404), None)
    traffic_analytics.record_http_request(bot_request, _html_response(500), None)

    traffic_analytics.record_http_request(_fake_request(path="/.env"), _html_response(404), None)

    minute_bucket = next(iter(traffic_analytics._MINUTE_BUCKETS.values()))
    assert minute_bucket["requests"] == 4
    assert minute_bucket["status_4xx"] == 1
    # 5xx 不区分来源，服务端异常必须完整计数
    assert minute_bucket["status_5xx"] == 1


def test_with_ratios_excludes_bot_and_suspicious_from_4xx_denominator():
    totals = {
        "requests": 100,
        "bot_requests": 40,
        "suspicious_requests": 30,
        "status_4xx": 6,
        "status_5xx": 0,
        "page_views": 0,
        "beacon_page_views": 0,
    }
    result = crud_traffic._with_ratios(totals)

    # 分母为真实用户请求 100 - 40 - 30 = 30，4xx 比例 = 6/30
    assert result["status_4xx_ratio"] == 20.0
    assert result["bot_ratio"] == 40.0
    assert result["suspicious_ratio"] == 30.0


def test_upsert_statements_compile_for_sqlite_and_postgresql():
    class _CapturingSession:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)

    now = utc_now_naive()
    minute_row = {
        "bucket_start": now.replace(second=0, microsecond=0),
        "requests": 1,
        "page_views": 1,
        "beacon_page_views": 0,
        "bot_requests": 0,
        "suspicious_requests": 0,
        "admin_requests": 0,
        "api_requests": 0,
        "htmx_requests": 0,
        "other_requests": 0,
        "status_4xx": 0,
        "status_5xx": 0,
        "duration_ms_sum": 12,
        "peak_concurrency": 1,
    }
    anomaly_row = {
        "ip": "198.51.100.10",
        "hits": 1,
        "reason": "测试",
        "sample_path": "/",
        "sample_user_agent": "curl/8.0",
        "first_seen": now,
        "last_seen": now,
    }

    for dialect_name, dialect in (
        ("sqlite", sqlite.dialect()),
        ("postgresql", postgresql.dialect()),
    ):
        session = _CapturingSession()
        traffic_analytics._upsert_minute_rows(session, [minute_row], dialect_name, now)
        traffic_analytics._upsert_anomaly_rows(session, [anomaly_row], dialect_name, now)
        compiled = [str(statement.compile(dialect=dialect)) for statement in session.statements]
        assert len(compiled) == 2
        assert all("ON CONFLICT" in sql for sql in compiled)
