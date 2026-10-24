"""访问统计缓冲与聚合写入

设计要点：
1. 请求内只更新有界内存缓冲，不做任何数据库写入
2. 独立异步循环每 15 秒批量 upsert，避免请求路径写库
3. 所有缓冲结构都有上限，数据库故障时最多保留约 3 小时分钟数据
4. 每日维度与 UV 采用“累计值判上限 + 增量快照刷库”，避免写放大
5. 统计失败只记 debug 日志，绝不影响正常请求

时间约定：所有数据库字段存无时区 UTC；每日维度的 day_start_utc 存
“站点自然日 00:00 对应的 UTC 时间”，由 site_day_start_utc() 生成。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    TrafficAnomalySource,
    TrafficDimensionDaily,
    TrafficHourStat,
    TrafficMinuteStat,
    TrafficVisitorDaily,
)
from ..schemas.setting import SettingCreate, SettingUpdate
from . import time_utils
from .admin_path import get_admin_path
from .config import settings
from .database import db_manager
from .traffic_classifier import (
    CATEGORY_ADMIN,
    CATEGORY_API,
    CATEGORY_BOT,
    CATEGORY_HTMX,
    CATEGORY_OTHER,
    CATEGORY_PAGE_VIEW,
    CATEGORY_SUSPICIOUS,
    classify_request,
    normalize_admin_path,
)

logger = logging.getLogger(__name__)

FLUSH_INTERVAL_SECONDS = 15
MINUTE_RETENTION_HOURS = 48
HOUR_RETENTION_DAYS = 365 * 3
ANOMALY_RETENTION_DAYS = 7
ANOMALY_MAX_ROWS = 500

# 前端 beacon 端点：公开页面上报页面浏览，用于覆盖 CDN 缓存命中的访问
BEACON_PATH = "/api/v1/traffic/pageview"
BEACON_MAX_BODY_BYTES = 2048
MAX_BEACON_PER_IP_MINUTE = 120

TRAFFIC_ENABLED_KEY = "traffic_analytics_enabled"
TRAFFIC_RETENTION_DAYS_KEY = "traffic_analytics_retention_days"
TRAFFIC_RESET_TOKEN_KEY = "traffic_analytics_reset_token"
TRAFFIC_LAST_CLEANED_KEY = "traffic_analytics_last_cleaned_at"

DEFAULT_RETENTION_DAYS = 365
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 730

_MAX_MINUTE_BUCKETS = 180
_MAX_HOUR_BUCKETS = 72
_MAX_VISITOR_HASHES_PER_DAY = 20000
_MAX_ANOMALY_PENDING = 2000
_MAX_IP_MINUTE_KEYS = 5000

_DIMENSION_LIMITS = {
    "path": 300,
    "referer": 200,
    "bot": 100,
    "source_type": 10,
    "utm_source": 50,
    "status": 20,
    # 前端上报的页面维度独立存放，避免与回源维度相加后重复计数
    "beacon_path": 300,
    "beacon_referer": 200,
    "beacon_source_type": 10,
    "beacon_utm_source": 50,
}
_OVERFLOW_VALUE = "__overflow__"

_COUNTER_FIELDS = (
    "requests",
    "page_views",
    "beacon_page_views",
    "bot_requests",
    "suspicious_requests",
    "admin_requests",
    "api_requests",
    "htmx_requests",
    "other_requests",
    "status_4xx",
    "status_5xx",
)
_CATEGORY_FIELD_MAP = {
    CATEGORY_PAGE_VIEW: "page_views",
    CATEGORY_BOT: "bot_requests",
    CATEGORY_SUSPICIOUS: "suspicious_requests",
    CATEGORY_ADMIN: "admin_requests",
    CATEGORY_API: "api_requests",
    CATEGORY_HTMX: "htmx_requests",
    CATEGORY_OTHER: "other_requests",
}

_LOCK = threading.RLock()
_MINUTE_BUCKETS: dict[datetime, dict[str, int]] = {}
_HOUR_BUCKETS: dict[datetime, dict[str, int]] = {}
_MINUTE_PEAKS: dict[datetime, int] = {}
_DIMENSION_VALUES: dict[datetime, dict[str, dict[str, int]]] = {}
_DIMENSION_FLUSHED: dict[datetime, dict[str, dict[str, int]]] = {}
_VISITOR_VALUES: dict[datetime, dict[str, int]] = {}
_VISITOR_FLUSHED: dict[datetime, dict[str, int]] = {}
_UV_OVERFLOW_DAYS: set[datetime] = set()
_ANOMALY_PENDING: dict[str, dict[str, Any]] = {}
_IP_MINUTE_COUNTS: dict[tuple[datetime, str], int] = {}
_BEACON_IP_MINUTE_COUNTS: dict[tuple[datetime, str], int] = {}

_ACTIVE_REQUESTS = 0
_ENABLED = True
_RESET_TOKEN = ""
_DROPPED_EVENTS = 0
_LAST_FLUSH_AT: datetime | None = None
_LAST_FLUSH_ERROR = ""
_FLUSH_TASK: asyncio.Task | None = None


def _new_counter_bucket() -> dict[str, int]:
    bucket = {field: 0 for field in _COUNTER_FIELDS}
    bucket["duration_ms_sum"] = 0
    return bucket


def _minute_start(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _hour_start(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _trim_dict(mapping: dict, limit: int) -> None:
    if len(mapping) <= limit:
        return
    for key in sorted(mapping)[: len(mapping) - limit]:
        del mapping[key]


def _trim_days(mapping: dict, keep: int = 3) -> None:
    if len(mapping) <= keep:
        return
    for key in sorted(mapping)[: len(mapping) - keep]:
        del mapping[key]


def is_enabled() -> bool:
    """统计开关的进程内缓存值，由刷写循环每 15 秒同步一次。"""
    return _ENABLED


def begin_request() -> None:
    """请求开始时记录并发峰值。"""
    global _ACTIVE_REQUESTS
    with _LOCK:
        _ACTIVE_REQUESTS += 1
        minute = _minute_start(time_utils.utc_now_naive())
        if _ACTIVE_REQUESTS > _MINUTE_PEAKS.get(minute, 0):
            _MINUTE_PEAKS[minute] = _ACTIVE_REQUESTS
        _trim_dict(_MINUTE_PEAKS, _MAX_MINUTE_BUCKETS)


def end_request() -> None:
    """请求结束时归还并发计数，保证增减平衡。"""
    global _ACTIVE_REQUESTS
    with _LOCK:
        if _ACTIVE_REQUESTS > 0:
            _ACTIVE_REQUESTS -= 1


def _get_client_ip(request) -> str:
    # 必须使用后台安全模块的实现：只信任配置的可信代理
    from .admin_security import get_client_ip

    try:
        return get_client_ip(request)
    except Exception:
        peer = getattr(getattr(request, "client", None), "host", "") or ""
        return peer or "unknown"


def _visitor_hash(ip: str) -> str:
    key = str(getattr(settings, "SECRET_KEY", "") or "").encode("utf-8")
    return hmac.new(key, str(ip or "").encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _sanitize_admin_path(path: str, admin_path: str) -> str:
    prefix = normalize_admin_path(admin_path)
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        return ("/<admin>" + path[len(prefix):])[:512]
    return path[:512]


def _add_dimension(day: datetime, kind: str, value: str) -> None:
    kinds = _DIMENSION_VALUES.setdefault(day, {})
    values = kinds.setdefault(kind, {})
    normalized = str(value or "")[:512] or "-"
    limit = _DIMENSION_LIMITS.get(kind, 100)
    if normalized not in values and len(values) >= limit:
        normalized = _OVERFLOW_VALUE
    values[normalized] = values.get(normalized, 0) + 1


def _add_visitor(day: datetime, ip: str) -> None:
    values = _VISITOR_VALUES.setdefault(day, {})
    visitor_hash = _visitor_hash(ip)
    if visitor_hash not in values:
        if len(values) >= _MAX_VISITOR_HASHES_PER_DAY:
            _UV_OVERFLOW_DAYS.add(day)
            if len(_UV_OVERFLOW_DAYS) > 3:
                _UV_OVERFLOW_DAYS.discard(min(_UV_OVERFLOW_DAYS))
            return
    values[visitor_hash] = values.get(visitor_hash, 0) + 1


def _add_anomaly(
    *,
    ip: str,
    reason: str,
    path: str,
    user_agent: str,
    admin_path: str,
    now: datetime,
) -> None:
    normalized_ip = str(ip or "unknown")[:45]
    entry = _ANOMALY_PENDING.get(normalized_ip)
    if entry is None:
        if len(_ANOMALY_PENDING) >= _MAX_ANOMALY_PENDING:
            victim_ip = min(
                _ANOMALY_PENDING,
                key=lambda key: (
                    _ANOMALY_PENDING[key]["hits"],
                    _ANOMALY_PENDING[key]["last_seen"],
                ),
            )
            _ANOMALY_PENDING.pop(victim_ip, None)
        entry = {
            "ip": normalized_ip,
            "hits": 0,
            "reason": "",
            "sample_path": "",
            "sample_user_agent": "",
            "first_seen": now,
            "last_seen": now,
        }
        _ANOMALY_PENDING[normalized_ip] = entry

    entry["hits"] += 1
    entry["last_seen"] = now
    if reason:
        entry["reason"] = reason[:100]
    entry["sample_path"] = _sanitize_admin_path(path, admin_path)
    entry["sample_user_agent"] = str(user_agent or "")[:255]


def _record_classification(
    classification,
    *,
    status_code: int,
    duration_ms: int,
    client_ip: str,
    user_agent: str,
    admin_path: str,
    now: datetime,
) -> None:
    minute = _minute_start(now)
    hour = _hour_start(now)

    minute_bucket = _MINUTE_BUCKETS.setdefault(minute, _new_counter_bucket())
    hour_bucket = _HOUR_BUCKETS.setdefault(hour, _new_counter_bucket())
    category_field = _CATEGORY_FIELD_MAP.get(classification.category, "other_requests")

    for bucket in (minute_bucket, hour_bucket):
        bucket["requests"] += 1
        bucket[category_field] += 1
        if 400 <= int(status_code) < 500:
            bucket["status_4xx"] += 1
        if int(status_code) >= 500:
            bucket["status_5xx"] += 1

    minute_bucket["duration_ms_sum"] += max(0, int(duration_ms or 0))
    _trim_dict(_MINUTE_BUCKETS, _MAX_MINUTE_BUCKETS)
    _trim_dict(_HOUR_BUCKETS, _MAX_HOUR_BUCKETS)

    day = time_utils.site_day_start_utc(now)
    _add_dimension(day, "status", str(int(status_code or 0)))
    if classification.page_view:
        _add_dimension(day, "path", classification.path)
        if classification.referer_host:
            _add_dimension(day, "referer", classification.referer_host)
        if classification.source_type:
            _add_dimension(day, "source_type", classification.source_type)
        if classification.utm_source:
            _add_dimension(day, "utm_source", classification.utm_source)
        _add_visitor(day, client_ip)
    if classification.category == CATEGORY_BOT and classification.bot_name:
        _add_dimension(day, "bot", classification.bot_name)
    if classification.suspicious_score >= 2:
        _add_anomaly(
            ip=client_ip,
            reason=classification.suspicious_reason,
            path=classification.path,
            user_agent=user_agent,
            admin_path=admin_path,
            now=now,
        )

    _trim_days(_DIMENSION_VALUES)
    _trim_days(_VISITOR_VALUES)


def _next_ip_minute_count(minute: datetime, client_ip: str) -> int:
    key = (minute, str(client_ip or "unknown"))
    count = _IP_MINUTE_COUNTS.get(key)
    if count is None and len(_IP_MINUTE_COUNTS) >= _MAX_IP_MINUTE_KEYS:
        oldest_minute = min(item[0] for item in _IP_MINUTE_COUNTS)
        stale_keys = [item for item in _IP_MINUTE_COUNTS if item[0] == oldest_minute]
        for stale in stale_keys:
            _IP_MINUTE_COUNTS.pop(stale, None)
        if len(_IP_MINUTE_COUNTS) >= _MAX_IP_MINUTE_KEYS:
            # 同一分钟内 IP 数量已到上限，放弃本次高频计数
            return 0
    count = int(_IP_MINUTE_COUNTS.get(key, 0)) + 1
    _IP_MINUTE_COUNTS[key] = count
    return count


def _take_beacon_slot(minute: datetime, client_ip: str) -> bool:
    """beacon 端点频控：同一 IP 每分钟最多记录固定条数，防止被刷爆。"""
    key = (minute, str(client_ip or "unknown"))
    count = int(_BEACON_IP_MINUTE_COUNTS.get(key, 0))
    if count >= MAX_BEACON_PER_IP_MINUTE:
        return False
    if key not in _BEACON_IP_MINUTE_COUNTS and len(_BEACON_IP_MINUTE_COUNTS) >= _MAX_IP_MINUTE_KEYS:
        oldest_minute = min(item[0] for item in _BEACON_IP_MINUTE_COUNTS)
        stale_keys = [item for item in _BEACON_IP_MINUTE_COUNTS if item[0] == oldest_minute]
        for stale in stale_keys:
            _BEACON_IP_MINUTE_COUNTS.pop(stale, None)
    _BEACON_IP_MINUTE_COUNTS[key] = count + 1
    return True


def record_beacon_page_view(
    request,
    *,
    path: str,
    referrer: str,
    query_string: str,
) -> None:
    """记录前端上报的页面浏览。

    只统计能判定为有效页面访问的上报；爬虫、后台路径与可疑上报直接忽略。
    该端点不写数据库，只进入有界内存缓冲，由刷写循环统一落库。
    """
    try:
        if not _ENABLED:
            return
        normalized_path = str(path or "").strip()
        # 仅接受站内绝对路径，拒绝协议相对与跨站地址
        if not normalized_path.startswith("/") or normalized_path.startswith("//"):
            return
        # 浏览器 location.search 自带前导 "?"，分类器按无 "?" 的 query 解析
        normalized_query = str(query_string or "").strip()
        if normalized_query.startswith("?"):
            normalized_query = normalized_query[1:]
        now = time_utils.utc_now_naive()
        client_ip = _get_client_ip(request)
        minute = _minute_start(now)
        with _LOCK:
            if not _take_beacon_slot(minute, client_ip):
                return
            _trim_dict(_BEACON_IP_MINUTE_COUNTS, _MAX_IP_MINUTE_KEYS)

        headers = request.headers
        classification = classify_request(
            path=normalized_path,
            method="GET",
            status_code=200,
            content_type="text/html",
            user_agent=headers.get("user-agent", ""),
            referer=referrer,
            query_string=normalized_query,
            site_host=headers.get("host", ""),
            admin_path=get_admin_path(),
            is_admin=False,
            is_htmx_request=False,
            requests_in_minute=0,
        )
        if classification.category != CATEGORY_PAGE_VIEW or not classification.page_view:
            return

        with _LOCK:
            minute_bucket = _MINUTE_BUCKETS.setdefault(minute, _new_counter_bucket())
            hour_bucket = _HOUR_BUCKETS.setdefault(_hour_start(now), _new_counter_bucket())
            minute_bucket["beacon_page_views"] += 1
            hour_bucket["beacon_page_views"] += 1
            _trim_dict(_MINUTE_BUCKETS, _MAX_MINUTE_BUCKETS)
            _trim_dict(_HOUR_BUCKETS, _MAX_HOUR_BUCKETS)

            day = time_utils.site_day_start_utc(now)
            _add_dimension(day, "beacon_path", classification.path)
            if classification.referer_host:
                _add_dimension(day, "beacon_referer", classification.referer_host)
            if classification.source_type:
                _add_dimension(day, "beacon_source_type", classification.source_type)
            if classification.utm_source:
                _add_dimension(day, "beacon_utm_source", classification.utm_source)
            _add_visitor(day, client_ip)
            _trim_days(_DIMENSION_VALUES)
            _trim_days(_VISITOR_VALUES)
    except Exception:
        logger.debug("访问统计 beacon 记录失败，已忽略", exc_info=True)


def record_http_request(
    request,
    response,
    started_perf: float | None,
    *,
    forced_status: int | None = None,
) -> None:
    """记录一次请求；任何异常都只写 debug 日志，绝不外抛。"""
    try:
        if not _ENABLED:
            return
        now = time_utils.utc_now_naive()
        headers = request.headers
        status_code = (
            int(forced_status)
            if forced_status is not None
            else int(getattr(response, "status_code", 0) or 0)
        )
        content_type = ""
        if response is not None:
            content_type = response.headers.get("content-type", "")
        duration_ms = 0
        if started_perf is not None:
            duration_ms = int(max(0.0, (time.perf_counter() - started_perf) * 1000))

        client_ip = _get_client_ip(request)
        minute = _minute_start(now)
        with _LOCK:
            requests_in_minute = _next_ip_minute_count(minute, client_ip)

        classification = classify_request(
            path=request.url.path,
            method=request.method,
            status_code=status_code,
            content_type=content_type,
            user_agent=headers.get("user-agent", ""),
            referer=headers.get("referer", ""),
            query_string=request.url.query,
            site_host=headers.get("host", ""),
            admin_path=get_admin_path(),
            is_admin=bool(getattr(request.state, "authenticated_user", None)),
            is_htmx_request=str(headers.get("hx-request", "")).strip().lower() == "true",
            requests_in_minute=requests_in_minute,
        )

        with _LOCK:
            _record_classification(
                classification,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=headers.get("user-agent", ""),
                admin_path=get_admin_path(),
                now=now,
            )
    except Exception:
        logger.debug("访问统计记录失败，已忽略", exc_info=True)


def get_live_snapshot(now: datetime | None = None) -> dict[str, Any]:
    """返回当前进程的内存实时快照，供突发与容量片段使用。"""
    current = now or time_utils.utc_now_naive()
    minute = _minute_start(current)
    with _LOCK:
        bucket = _MINUTE_BUCKETS.get(minute)
        return {
            "current_minute_requests": int(bucket["requests"]) if bucket else 0,
            "current_minute_page_views": int(bucket["page_views"]) if bucket else 0,
            "current_minute_beacon_page_views": int(bucket["beacon_page_views"]) if bucket else 0,
            "active_concurrency": _ACTIVE_REQUESTS,
            "peak_concurrency_current_minute": int(_MINUTE_PEAKS.get(minute, 0)),
            "dropped_events": _DROPPED_EVENTS,
            "last_flush_at": _LAST_FLUSH_AT,
            "last_flush_error": _LAST_FLUSH_ERROR,
            "enabled": _ENABLED,
            "uv_approximate": time_utils.site_day_start_utc(current) in _UV_OVERFLOW_DAYS,
        }


def _take_flush_snapshot() -> dict[str, Any]:
    with _LOCK:
        minute_rows = []
        for bucket_start, counts in _MINUTE_BUCKETS.items():
            row = {"bucket_start": bucket_start}
            row.update({field: int(counts.get(field, 0)) for field in _COUNTER_FIELDS})
            row["duration_ms_sum"] = int(counts.get("duration_ms_sum", 0))
            row["peak_concurrency"] = int(_MINUTE_PEAKS.get(bucket_start, 0))
            minute_rows.append(row)
        _MINUTE_BUCKETS.clear()
        _MINUTE_PEAKS.clear()

        hour_rows = []
        for bucket_start, counts in _HOUR_BUCKETS.items():
            row = {"bucket_start": bucket_start}
            row.update({field: int(counts.get(field, 0)) for field in _COUNTER_FIELDS})
            hour_rows.append(row)
        _HOUR_BUCKETS.clear()

        dimension_rows = []
        dimension_state: dict[datetime, dict[str, dict[str, int]]] = {}
        for day, kinds in _DIMENSION_VALUES.items():
            flushed_day = _DIMENSION_FLUSHED.get(day, {})
            for kind, values in kinds.items():
                flushed_kind = flushed_day.get(kind, {})
                for value, total in values.items():
                    delta = int(total) - int(flushed_kind.get(value, 0))
                    if delta > 0:
                        dimension_rows.append(
                            {
                                "day_start_utc": day,
                                "kind": kind,
                                "value": value[:512],
                                "hits": delta,
                            }
                        )
            dimension_state[day] = {
                kind: dict(values) for kind, values in kinds.items()
            }

        visitor_rows = []
        visitor_state: dict[datetime, dict[str, int]] = {}
        for day, values in _VISITOR_VALUES.items():
            flushed = _VISITOR_FLUSHED.get(day, {})
            for visitor_hash, total in values.items():
                delta = int(total) - int(flushed.get(visitor_hash, 0))
                if delta > 0:
                    visitor_rows.append(
                        {
                            "day_start_utc": day,
                            "visitor_hash": visitor_hash,
                            "hits": delta,
                        }
                    )
            visitor_state[day] = dict(values)

        anomaly_rows = list(_ANOMALY_PENDING.values())
        _ANOMALY_PENDING.clear()

        return {
            "minute_rows": minute_rows,
            "hour_rows": hour_rows,
            "dimension_rows": dimension_rows,
            "dimension_state": dimension_state,
            "visitor_rows": visitor_rows,
            "visitor_state": visitor_state,
            "anomaly_rows": [
                {
                    "ip": row["ip"],
                    "hits": int(row["hits"]),
                    "reason": row["reason"],
                    "sample_path": row["sample_path"],
                    "sample_user_agent": row["sample_user_agent"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                }
                for row in anomaly_rows
            ],
        }


def _merge_counter_rows(target: dict[datetime, dict[str, int]], rows: list[dict], limit: int) -> None:
    global _DROPPED_EVENTS
    for row in rows:
        bucket_start = row["bucket_start"]
        bucket = target.setdefault(bucket_start, _new_counter_bucket())
        for field in _COUNTER_FIELDS:
            bucket[field] += int(row.get(field, 0))
        bucket["duration_ms_sum"] += int(row.get("duration_ms_sum", 0))
    while len(target) > limit:
        oldest = min(target)
        _DROPPED_EVENTS += int(target[oldest].get("requests", 0))
        del target[oldest]


def _restore_snapshot(snapshot: dict[str, Any]) -> None:
    with _LOCK:
        _merge_counter_rows(_MINUTE_BUCKETS, snapshot["minute_rows"], _MAX_MINUTE_BUCKETS)
        _merge_counter_rows(_HOUR_BUCKETS, snapshot["hour_rows"], _MAX_HOUR_BUCKETS)
        for row in snapshot["minute_rows"]:
            bucket_start = row["bucket_start"]
            peak = int(row.get("peak_concurrency", 0))
            if peak > _MINUTE_PEAKS.get(bucket_start, 0):
                _MINUTE_PEAKS[bucket_start] = peak
        _trim_dict(_MINUTE_PEAKS, _MAX_MINUTE_BUCKETS)

        for row in snapshot["anomaly_rows"]:
            existing = _ANOMALY_PENDING.get(row["ip"])
            if existing is None:
                if len(_ANOMALY_PENDING) >= _MAX_ANOMALY_PENDING:
                    continue
                _ANOMALY_PENDING[row["ip"]] = dict(row)
                continue
            existing["hits"] += int(row["hits"])
            if row["first_seen"] < existing["first_seen"]:
                existing["first_seen"] = row["first_seen"]
            if row["last_seen"] > existing["last_seen"]:
                existing["last_seen"] = row["last_seen"]
            if row["reason"]:
                existing["reason"] = row["reason"]
            existing["sample_path"] = row["sample_path"]
            existing["sample_user_agent"] = row["sample_user_agent"]


def _commit_state(snapshot: dict[str, Any]) -> None:
    with _LOCK:
        for day, kinds in snapshot["dimension_state"].items():
            _DIMENSION_FLUSHED[day] = {
                kind: dict(values) for kind, values in kinds.items()
            }
        for day, values in snapshot["visitor_state"].items():
            _VISITOR_FLUSHED[day] = dict(values)
        _trim_days(_DIMENSION_FLUSHED)
        _trim_days(_VISITOR_FLUSHED)


def _insert_factory(dialect_name: str):
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        return insert
    from sqlalchemy.dialects.sqlite import insert

    return insert


def _upsert_minute_rows(session: Session, rows: list[dict], dialect_name: str, now: datetime) -> None:
    if not rows:
        return
    table = TrafficMinuteStat.__table__
    stmt = _insert_factory(dialect_name)(table).values(rows)
    set_map = {
        field: table.c[field] + stmt.excluded[field] for field in _COUNTER_FIELDS
    }
    set_map["duration_ms_sum"] = table.c.duration_ms_sum + stmt.excluded.duration_ms_sum
    if dialect_name == "postgresql":
        set_map["peak_concurrency"] = func.greatest(
            table.c.peak_concurrency, stmt.excluded.peak_concurrency
        )
    else:
        set_map["peak_concurrency"] = func.max(
            table.c.peak_concurrency, stmt.excluded.peak_concurrency
        )
    set_map["updated_at"] = now
    session.execute(
        stmt.on_conflict_do_update(index_elements=[table.c.bucket_start], set_=set_map)
    )


def _upsert_hour_rows(session: Session, rows: list[dict], dialect_name: str, now: datetime) -> None:
    if not rows:
        return
    table = TrafficHourStat.__table__
    stmt = _insert_factory(dialect_name)(table).values(rows)
    set_map = {
        field: table.c[field] + stmt.excluded[field] for field in _COUNTER_FIELDS
    }
    set_map["updated_at"] = now
    session.execute(
        stmt.on_conflict_do_update(index_elements=[table.c.bucket_start], set_=set_map)
    )


def _upsert_dimension_rows(session: Session, rows: list[dict], dialect_name: str, now: datetime) -> None:
    if not rows:
        return
    table = TrafficDimensionDaily.__table__
    stmt = _insert_factory(dialect_name)(table).values(rows)
    set_map = {
        "hits": table.c.hits + stmt.excluded.hits,
        "updated_at": now,
    }
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["day_start_utc", "kind", "value"], set_=set_map
        )
    )


def _upsert_visitor_rows(session: Session, rows: list[dict], dialect_name: str, now: datetime) -> None:
    if not rows:
        return
    table = TrafficVisitorDaily.__table__
    stmt = _insert_factory(dialect_name)(table).values(rows)
    set_map = {
        "hits": table.c.hits + stmt.excluded.hits,
        "updated_at": now,
    }
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["day_start_utc", "visitor_hash"], set_=set_map
        )
    )


def _upsert_anomaly_rows(session: Session, rows: list[dict], dialect_name: str, now: datetime) -> None:
    if not rows:
        return
    table = TrafficAnomalySource.__table__
    stmt = _insert_factory(dialect_name)(table).values(rows)
    set_map = {
        "hits": table.c.hits + stmt.excluded.hits,
        "reason": stmt.excluded.reason,
        "sample_path": stmt.excluded.sample_path,
        "sample_user_agent": stmt.excluded.sample_user_agent,
        "updated_at": now,
    }
    if dialect_name == "postgresql":
        set_map["first_seen"] = func.least(table.c.first_seen, stmt.excluded.first_seen)
        set_map["last_seen"] = func.greatest(table.c.last_seen, stmt.excluded.last_seen)
    else:
        set_map["first_seen"] = func.min(table.c.first_seen, stmt.excluded.first_seen)
        set_map["last_seen"] = func.max(table.c.last_seen, stmt.excluded.last_seen)
    session.execute(
        stmt.on_conflict_do_update(index_elements=["ip"], set_=set_map)
    )


def _read_runtime_settings(session: Session) -> tuple[bool, str]:
    from ..crud import setting as crud_setting

    values = crud_setting.get_settings_by_keys(
        session, [TRAFFIC_ENABLED_KEY, TRAFFIC_RESET_TOKEN_KEY]
    )
    enabled_raw = values.get(TRAFFIC_ENABLED_KEY)
    enabled = True if enabled_raw is None else bool(enabled_raw)
    return enabled, str(values.get(TRAFFIC_RESET_TOKEN_KEY) or "")


def _apply_runtime_state(enabled: bool, reset_token: str) -> None:
    global _ENABLED, _RESET_TOKEN
    with _LOCK:
        if _RESET_TOKEN and reset_token != _RESET_TOKEN:
            # 其他 worker 或本进程执行了清空，丢弃旧缓冲
            _clear_buffers_locked()
        _RESET_TOKEN = reset_token
        _ENABLED = enabled


def _flush_once() -> None:
    global _LAST_FLUSH_AT, _LAST_FLUSH_ERROR
    session = db_manager.get_session()
    if session is None:
        return
    snapshot: dict[str, Any] | None = None
    try:
        enabled, reset_token = _read_runtime_settings(session)
        _apply_runtime_state(enabled, reset_token)

        snapshot = _take_flush_snapshot()
        has_rows = any(
            snapshot[key]
            for key in (
                "minute_rows",
                "hour_rows",
                "dimension_rows",
                "visitor_rows",
                "anomaly_rows",
            )
        )
        if not has_rows:
            _commit_state(snapshot)
            _LAST_FLUSH_AT = time_utils.utc_now_naive()
            _LAST_FLUSH_ERROR = ""
            return

        dialect_name = str(session.get_bind().dialect.name or "sqlite").lower()
        now = time_utils.utc_now_naive()
        _upsert_minute_rows(session, snapshot["minute_rows"], dialect_name, now)
        _upsert_hour_rows(session, snapshot["hour_rows"], dialect_name, now)
        _upsert_dimension_rows(session, snapshot["dimension_rows"], dialect_name, now)
        _upsert_visitor_rows(session, snapshot["visitor_rows"], dialect_name, now)
        _upsert_anomaly_rows(session, snapshot["anomaly_rows"], dialect_name, now)
        session.commit()

        _commit_state(snapshot)
        _LAST_FLUSH_AT = now
        _LAST_FLUSH_ERROR = ""
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        if snapshot is not None:
            _restore_snapshot(snapshot)
        _LAST_FLUSH_ERROR = str(exc)[:200]
        logger.warning("访问统计刷写失败，已回填内存缓冲: %s", exc)
    finally:
        try:
            session.close()
        except Exception:
            pass


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(_flush_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("访问统计刷写循环异常")


def _refresh_runtime_state_once() -> None:
    session = db_manager.get_session()
    if session is None:
        return
    try:
        enabled, reset_token = _read_runtime_settings(session)
        _apply_runtime_state(enabled, reset_token)
    except Exception:
        logger.debug("访问统计读取开关失败", exc_info=True)
    finally:
        session.close()


async def start_flush_loop() -> None:
    """启动 15 秒刷写循环；启动前先同步一次开关状态。"""
    global _FLUSH_TASK
    if _FLUSH_TASK is not None and not _FLUSH_TASK.done():
        return
    await asyncio.to_thread(_refresh_runtime_state_once)
    _FLUSH_TASK = asyncio.create_task(_flush_loop(), name="rewrz-traffic-flush")


async def stop_flush_loop() -> None:
    """停止刷写循环，并做最后一次同步刷写。"""
    global _FLUSH_TASK
    task = _FLUSH_TASK
    _FLUSH_TASK = None
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await asyncio.to_thread(_flush_once)


def _clear_buffers_locked() -> None:
    global _DROPPED_EVENTS
    for mapping in (
        _MINUTE_BUCKETS,
        _HOUR_BUCKETS,
        _MINUTE_PEAKS,
        _DIMENSION_VALUES,
        _DIMENSION_FLUSHED,
        _VISITOR_VALUES,
        _VISITOR_FLUSHED,
        _ANOMALY_PENDING,
        _IP_MINUTE_COUNTS,
        _BEACON_IP_MINUTE_COUNTS,
    ):
        mapping.clear()
    _UV_OVERFLOW_DAYS.clear()
    _DROPPED_EVENTS = 0


def reset_buffers() -> None:
    """清空本进程的统计缓冲（清空统计时调用）。"""
    with _LOCK:
        _clear_buffers_locked()


def reset_for_tests() -> None:
    """测试用：重置全部内存状态。"""
    global _ENABLED, _RESET_TOKEN, _ACTIVE_REQUESTS, _LAST_FLUSH_AT, _LAST_FLUSH_ERROR
    with _LOCK:
        _clear_buffers_locked()
        _ACTIVE_REQUESTS = 0
        _ENABLED = True
        _RESET_TOKEN = ""
        _LAST_FLUSH_AT = None
        _LAST_FLUSH_ERROR = ""


def _upsert_setting(db: Session, key: str, value, *, description: str, type_name: str) -> None:
    from ..crud import setting as crud_setting

    existing = crud_setting.get_setting(db, key)
    if existing is None:
        crud_setting.create_setting(
            db,
            SettingCreate(
                key=key,
                value={"value": value},
                description=description,
                category="traffic",
                type=type_name,
            ),
        )
        return
    crud_setting.update_setting(
        db,
        key,
        SettingUpdate(value={"value": value}, description=description, type=type_name),
    )


def _normalize_retention_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    return max(MIN_RETENTION_DAYS, min(MAX_RETENTION_DAYS, days))


def get_analytics_settings(db: Session) -> dict[str, Any]:
    """读取统计设置，缺失时返回默认值。"""
    from ..crud import setting as crud_setting

    values = crud_setting.get_settings_by_keys(
        db,
        [
            TRAFFIC_ENABLED_KEY,
            TRAFFIC_RETENTION_DAYS_KEY,
            TRAFFIC_LAST_CLEANED_KEY,
        ],
    )
    enabled_raw = values.get(TRAFFIC_ENABLED_KEY)
    return {
        "enabled": True if enabled_raw is None else bool(enabled_raw),
        "retention_days": _normalize_retention_days(
            values.get(TRAFFIC_RETENTION_DAYS_KEY, DEFAULT_RETENTION_DAYS)
        ),
        "last_cleaned_at": str(values.get(TRAFFIC_LAST_CLEANED_KEY) or ""),
    }


def save_analytics_settings(db: Session, *, enabled: bool, retention_days: int) -> dict[str, Any]:
    """保存开关与保留天数，并立即同步进程内开关。"""
    global _ENABLED
    normalized_days = _normalize_retention_days(retention_days)
    _upsert_setting(
        db,
        TRAFFIC_ENABLED_KEY,
        bool(enabled),
        description="是否启用访问统计",
        type_name="boolean",
    )
    _upsert_setting(
        db,
        TRAFFIC_RETENTION_DAYS_KEY,
        normalized_days,
        description="访问统计维度与 UV 保留天数",
        type_name="integer",
    )
    db.commit()
    with _LOCK:
        _ENABLED = bool(enabled)
    return {"enabled": bool(enabled), "retention_days": normalized_days}


def clear_analytics_data(db: Session) -> None:
    """清空全部统计表，并广播清空令牌。"""
    for model in (
        TrafficMinuteStat,
        TrafficHourStat,
        TrafficDimensionDaily,
        TrafficVisitorDaily,
        TrafficAnomalySource,
    ):
        db.query(model).delete(synchronize_session=False)
    _upsert_setting(
        db,
        TRAFFIC_RESET_TOKEN_KEY,
        secrets.token_hex(8),
        description="访问统计清空令牌，用于通知其他 worker 丢弃缓冲",
        type_name="string",
    )
    db.commit()
    reset_buffers()


def cleanup_traffic_data(retention_days: int | None = None) -> dict[str, int]:
    """按保留期清理统计表；按表分别提交，单表失败不影响其他表。"""
    session = db_manager.get_session()
    if session is None:
        return {}

    now = time_utils.utc_now_naive()
    if retention_days is None:
        retention_days = get_analytics_settings(session)["retention_days"]
    normalized_days = _normalize_retention_days(retention_days)

    counts: dict[str, int] = {}
    cleanup_plan = (
        ("minute_stats", TrafficMinuteStat, TrafficMinuteStat.bucket_start,
         now - timedelta(hours=MINUTE_RETENTION_HOURS)),
        ("hour_stats", TrafficHourStat, TrafficHourStat.bucket_start,
         now - timedelta(days=HOUR_RETENTION_DAYS)),
        ("dimensions", TrafficDimensionDaily, TrafficDimensionDaily.day_start_utc,
         time_utils.site_day_start_utc(now - timedelta(days=normalized_days))),
        ("visitors", TrafficVisitorDaily, TrafficVisitorDaily.day_start_utc,
         time_utils.site_day_start_utc(now - timedelta(days=normalized_days))),
        ("anomalies", TrafficAnomalySource, TrafficAnomalySource.last_seen,
         now - timedelta(days=ANOMALY_RETENTION_DAYS)),
    )

    try:
        for name, model, column, cutoff in cleanup_plan:
            try:
                deleted = (
                    session.execute(delete(model).where(column < cutoff))
                    .rowcount
                    or 0
                )
                session.commit()
                counts[name] = int(deleted)
            except Exception:
                session.rollback()
                logger.debug("访问统计清理失败: %s", name, exc_info=True)

        try:
            keep_ids = (
                select(TrafficAnomalySource.id)
                .order_by(
                    TrafficAnomalySource.hits.desc(),
                    TrafficAnomalySource.last_seen.desc(),
                )
                .offset(ANOMALY_MAX_ROWS)
            )
            deleted = (
                session.execute(
                    delete(TrafficAnomalySource).where(
                        TrafficAnomalySource.id.in_(keep_ids)
                    )
                ).rowcount
                or 0
            )
            session.commit()
            counts["anomalies_trimmed"] = int(deleted)
        except Exception:
            session.rollback()
            logger.debug("访问统计异常来源裁剪失败", exc_info=True)

        try:
            _upsert_setting(
                session,
                TRAFFIC_LAST_CLEANED_KEY,
                time_utils.utc_iso(now),
                description="访问统计最近一次自动清理时间",
                type_name="string",
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.debug("访问统计清理时间写入失败", exc_info=True)
    finally:
        session.close()
    return counts
