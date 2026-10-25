"""访问统计查询层

所有数据库时间都是无时区 UTC；查询时在 Python 中按站点时区聚合，
不在 SQL 里做方言相关的日期截断。统计表缺失或查询异常时返回空结构，
保证后台页面与仪表盘不会因为统计功能未就绪而 500。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    TrafficAnomalySource,
    TrafficDimensionDaily,
    TrafficHourStat,
    TrafficMinuteStat,
    TrafficVisitorDaily,
)
from ..core.database import db_manager
from ..core.time_utils import (
    format_site_time,
    get_site_timezone,
    site_now,
    to_site_time,
    utc_now_naive,
)

VALID_RANGES = ("today", "week", "month", "year", "recent_years", "custom")

RANGE_LABELS = {
    "today": "今日",
    "week": "本周",
    "month": "本月",
    "year": "今年",
    "recent_years": "近三年",
    "custom": "自定义",
}

SOURCE_TYPE_LABELS = {
    "direct": "直接访问",
    "internal": "站内跳转",
    "search": "搜索引擎",
    "social": "社交媒体",
    "external": "外链",
}

COMPOSITION_LABELS = {
    "page_views": "回源页面访问",
    "bot_requests": "爬虫",
    "suspicious_requests": "可疑请求",
    "admin_requests": "后台访问",
    "api_requests": "API / Feed",
    "htmx_requests": "HTMX 片段",
    "other_requests": "其他",
}

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

_CAPACITY_THRESHOLDS = {
    "peak_rpm_migrate": 300,
    "peak_concurrency_migrate": 40,
    "peak_concurrency_watch": 20,
    "five_xx_ratio_migrate": 0.01,
    "peak_rpm_watch": 150,
    "four_xx_ratio_watch": 0.10,
}

# 查询异常时的完整兜底结构：模板会链式访问 metrics 等字段，
# 用空字典会导致 Jinja Undefined 访问报错，统计页反而 500。
_EMPTY_BURST = {
    "minutes": [],
    "current_rpm": 0,
    "baseline_rpm": 0,
    "ratio": 0,
    "peak_concurrency": 0,
    "burst": False,
    "burst_label": "流量平稳",
    "active_concurrency": 0,
    "dropped_events": 0,
    "last_flush_at": "",
    "last_flush_error": "",
}

_EMPTY_CAPACITY = {
    "verdict": "unknown",
    "verdict_label": "容量状态未知",
    "summary": "暂无容量结论",
    "reasons": [],
    "watch_reasons": [],
    "metrics": {
        "peak_rpm": 0,
        "peak_concurrency": 0,
        "requests_48h": 0,
        "avg_duration_ms": 0,
        "status_4xx_ratio": 0,
        "status_5xx_ratio": 0,
        "pool_size": 0,
        "pool_checked_out": 0,
        "pool_timeout_count": 0,
        "dialect": "-",
    },
}


class TrafficRangeError(ValueError):
    """统计范围参数非法。"""


@dataclass(frozen=True)
class TrafficPeriod:
    range_key: str
    label: str
    start_utc: datetime
    end_utc: datetime
    data_end_utc: datetime
    granularity: str
    previous_start_utc: datetime
    previous_end_utc: datetime
    display_start: str
    display_end: str
    custom_start: str = ""
    custom_end: str = ""


def _local_to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_site_timezone())
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_date(raw: str | None, field_name: str) -> date:
    text = str(raw or "").strip()
    if not text:
        raise TrafficRangeError(f"请填写{field_name}")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise TrafficRangeError(f"{field_name}格式必须为 YYYY-MM-DD") from exc


def _auto_granularity(start_local: datetime, end_local: datetime) -> str:
    span_days = (end_local - start_local).total_seconds() / 86400
    if span_days <= 2:
        return "hour"
    if span_days <= 62:
        return "day"
    if span_days <= 730:
        return "month"
    return "year"


def build_period(
    range_key: str | None,
    start: str | None = None,
    end: str | None = None,
    *,
    now_utc: datetime | None = None,
) -> TrafficPeriod:
    """把范围参数解析为站点时区的自然周期，并转换为 UTC 区间。"""
    normalized_key = str(range_key or "today").strip().lower()
    if normalized_key not in VALID_RANGES:
        raise TrafficRangeError("统计范围不合法")

    current_utc = now_utc or utc_now_naive()
    site_tz = get_site_timezone()
    site_today = current_utc.replace(tzinfo=timezone.utc).astimezone(site_tz).date()

    if normalized_key == "today":
        start_local = datetime.combine(site_today, time.min, tzinfo=site_tz)
        end_local = start_local + timedelta(days=1)
        granularity = "hour"
        custom_start = custom_end = ""
    elif normalized_key == "week":
        week_start = site_today - timedelta(days=site_today.weekday())
        start_local = datetime.combine(week_start, time.min, tzinfo=site_tz)
        end_local = start_local + timedelta(days=7)
        granularity = "day"
        custom_start = custom_end = ""
    elif normalized_key == "month":
        start_local = datetime(site_today.year, site_today.month, 1, tzinfo=site_tz)
        if site_today.month == 12:
            end_local = datetime(site_today.year + 1, 1, 1, tzinfo=site_tz)
        else:
            end_local = datetime(site_today.year, site_today.month + 1, 1, tzinfo=site_tz)
        granularity = "day"
        custom_start = custom_end = ""
    elif normalized_key == "year":
        start_local = datetime(site_today.year, 1, 1, tzinfo=site_tz)
        end_local = datetime(site_today.year + 1, 1, 1, tzinfo=site_tz)
        granularity = "month"
        custom_start = custom_end = ""
    elif normalized_key == "recent_years":
        start_local = datetime(site_today.year - 2, 1, 1, tzinfo=site_tz)
        end_local = datetime(site_today.year + 1, 1, 1, tzinfo=site_tz)
        granularity = "year"
        custom_start = custom_end = ""
    else:
        start_date = _parse_date(start, "开始日期")
        end_date = _parse_date(end, "结束日期")
        if start_date > end_date:
            raise TrafficRangeError("开始日期不能晚于结束日期")
        start_local = datetime.combine(start_date, time.min, tzinfo=site_tz)
        end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=site_tz)
        granularity = _auto_granularity(start_local, end_local)
        custom_start = start_date.isoformat()
        custom_end = end_date.isoformat()

    start_utc = _local_to_utc_naive(start_local)
    end_utc = _local_to_utc_naive(end_local)
    data_end_utc = min(end_utc, current_utc)
    if data_end_utc < start_utc:
        data_end_utc = start_utc

    site_current = current_utc.replace(tzinfo=timezone.utc).astimezone(site_tz)
    if site_current < start_local:
        site_current = start_local
    if site_current > end_local:
        site_current = end_local
    elapsed = site_current - start_local
    span = end_local - start_local

    # 上一周期按“相同已过时长”对比，避免今日上午直接对比昨日全天
    if normalized_key == "today":
        previous_start_local = start_local - timedelta(days=1)
    elif normalized_key == "week":
        previous_start_local = start_local - timedelta(days=7)
    elif normalized_key == "month":
        if start_local.month == 1:
            previous_start_local = datetime(start_local.year - 1, 12, 1, tzinfo=site_tz)
        else:
            previous_start_local = datetime(
                start_local.year, start_local.month - 1, 1, tzinfo=site_tz
            )
    elif normalized_key == "year":
        previous_start_local = datetime(start_local.year - 1, 1, 1, tzinfo=site_tz)
    elif normalized_key == "recent_years":
        previous_start_local = datetime(start_local.year - 3, 1, 1, tzinfo=site_tz)
    else:
        previous_start_local = start_local - span

    previous_end_local = previous_start_local + elapsed
    if previous_end_local > start_local:
        previous_end_local = start_local
    previous_start_utc = _local_to_utc_naive(previous_start_local)
    previous_end_utc = _local_to_utc_naive(previous_end_local)

    return TrafficPeriod(
        range_key=normalized_key,
        label=RANGE_LABELS.get(normalized_key, "统计"),
        start_utc=start_utc,
        end_utc=end_utc,
        data_end_utc=data_end_utc,
        granularity=granularity,
        previous_start_utc=previous_start_utc,
        previous_end_utc=previous_end_utc,
        display_start=start_local.strftime("%Y-%m-%d"),
        display_end=(end_local - timedelta(seconds=1)).strftime("%Y-%m-%d"),
        custom_start=custom_start,
        custom_end=custom_end,
    )


def _sum_hour_rows(rows: Iterable[TrafficHourStat]) -> dict[str, int]:
    totals = {field: 0 for field in _COUNTER_FIELDS}
    for row in rows:
        for field in _COUNTER_FIELDS:
            totals[field] += int(getattr(row, field, 0) or 0)
    return totals


def _with_ratios(totals: dict[str, Any]) -> dict[str, Any]:
    requests = int(totals.get("requests", 0) or 0)
    page_views = int(totals.get("page_views", 0) or 0)
    beacon_page_views = int(totals.get("beacon_page_views", 0) or 0)
    # 有效访问取回源与前端上报的较大值：上报能覆盖 CDN 缓存命中，
    # 而回源 PV 能兜住未执行 JS 或上报被拦截的访问，避免被少量上报拉低。
    totals["effective_page_views"] = max(page_views, beacon_page_views)
    for ratio_field in (
        "bot_ratio",
        "suspicious_ratio",
        "page_view_ratio",
        "status_4xx_ratio",
        "status_5xx_ratio",
    ):
        totals[ratio_field] = 0.0
    if requests > 0:
        totals["bot_ratio"] = round(int(totals.get("bot_requests", 0)) * 100.0 / requests, 2)
        totals["suspicious_ratio"] = round(
            int(totals.get("suspicious_requests", 0)) * 100.0 / requests, 2
        )
        totals["page_view_ratio"] = round(page_views * 100.0 / requests, 2)
        totals["status_4xx_ratio"] = round(
            int(totals.get("status_4xx", 0)) * 100.0 / requests, 2
        )
        totals["status_5xx_ratio"] = round(
            int(totals.get("status_5xx", 0)) * 100.0 / requests, 2
        )
    return totals


def _fetch_hour_rows(db: Session, start_utc: datetime, end_utc: datetime) -> list[TrafficHourStat]:
    if end_utc <= start_utc:
        return []
    stmt = (
        select(TrafficHourStat)
        .where(
            TrafficHourStat.bucket_start >= start_utc,
            TrafficHourStat.bucket_start < end_utc,
        )
        .order_by(TrafficHourStat.bucket_start.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _fetch_minute_rows(db: Session, start_utc: datetime, end_utc: datetime) -> list[TrafficMinuteStat]:
    if end_utc <= start_utc:
        return []
    stmt = (
        select(TrafficMinuteStat)
        .where(
            TrafficMinuteStat.bucket_start >= start_utc,
            TrafficMinuteStat.bucket_start < end_utc,
        )
        .order_by(TrafficMinuteStat.bucket_start.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _bucket_key(site_dt: datetime, granularity: str):
    if granularity == "hour":
        return site_dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return site_dt.date()
    if granularity == "month":
        return (site_dt.year, site_dt.month)
    return site_dt.year


def _bucket_label(key, granularity: str, multi_day: bool) -> str:
    if granularity == "hour":
        return key.strftime("%m-%d %H:%M") if multi_day else key.strftime("%H:%M")
    if granularity == "day":
        return key.strftime("%m-%d")
    if granularity == "month":
        return f"{key[0]}-{key[1]:02d}"
    return str(key)


def _iter_bucket_keys(
    start_local: datetime, end_local: datetime, granularity: str
) -> list[Any]:
    keys: list[Any] = []
    if granularity == "hour":
        current = start_local.replace(minute=0, second=0, microsecond=0)
        while current <= end_local:
            keys.append(current)
            current = current + timedelta(hours=1)
    elif granularity == "day":
        current = start_local.date()
        end_date = end_local.date()
        while current <= end_date:
            keys.append(current)
            current = current + timedelta(days=1)
    elif granularity == "month":
        year, month = start_local.year, start_local.month
        while (year, month) <= (end_local.year, end_local.month):
            keys.append((year, month))
            month += 1
            if month > 12:
                month = 1
                year += 1
    else:
        for year in range(start_local.year, end_local.year + 1):
            keys.append(year)
    return keys


def _build_trend(
    rows: list[TrafficHourStat],
    period: TrafficPeriod,
    *,
    data_end_utc: datetime,
) -> list[dict[str, Any]]:
    site_tz = get_site_timezone()
    start_site = period.start_utc.replace(tzinfo=timezone.utc).astimezone(site_tz)
    end_site = max(data_end_utc, period.start_utc).replace(tzinfo=timezone.utc).astimezone(site_tz)
    keys = _iter_bucket_keys(start_site, end_site, period.granularity)
    if not keys:
        return []

    values: dict[Any, dict[str, int]] = {
        key: {"requests": 0, "page_views": 0, "beacon_page_views": 0} for key in keys
    }
    for row in rows:
        site_dt = to_site_time(row.bucket_start)
        if site_dt is None:
            continue
        key = _bucket_key(site_dt, period.granularity)
        if key not in values:
            values[key] = {"requests": 0, "page_views": 0, "beacon_page_views": 0}
        values[key]["requests"] += int(row.requests or 0)
        values[key]["page_views"] += int(row.page_views or 0)
        values[key]["beacon_page_views"] += int(row.beacon_page_views or 0)

    effective_values = {
        key: max(item["page_views"], item["beacon_page_views"])
        for key, item in values.items()
    }

    ordered_keys = sorted(values.keys())
    max_requests = max((item["requests"] for item in values.values()), default=0) or 1
    max_page_views = max(effective_values.values(), default=0) or 1
    count = len(ordered_keys)
    multi_day = (end_site.date() - start_site.date()).days >= 1

    trend = []
    for index, key in enumerate(ordered_keys):
        item = values[key]
        effective_page_views = effective_values[key]
        x_pct = 50.0 if count <= 1 else round(index * 100.0 / (count - 1), 2)
        trend.append(
            {
                "label": _bucket_label(key, period.granularity, multi_day),
                "requests": item["requests"],
                "page_views": item["page_views"],
                "beacon_page_views": item["beacon_page_views"],
                "effective_page_views": effective_page_views,
                "requests_pct": round(item["requests"] * 100.0 / max_requests, 2),
                "page_views_pct": round(effective_page_views * 100.0 / max_page_views, 2),
                "x_pct": x_pct,
            }
        )
    return trend


def _dimension_totals(
    db: Session,
    start_utc: datetime,
    end_utc: datetime,
    kind: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            TrafficDimensionDaily.value,
            func.sum(TrafficDimensionDaily.hits).label("hits"),
        )
        .where(
            TrafficDimensionDaily.day_start_utc >= start_utc,
            TrafficDimensionDaily.day_start_utc < end_utc,
            TrafficDimensionDaily.kind == kind,
        )
        .group_by(TrafficDimensionDaily.value)
        .order_by(func.sum(TrafficDimensionDaily.hits).desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).all()
    return [
        {"value": row[0], "hits": int(row[1] or 0)}
        for row in rows
        if row[0] is not None
    ]


def _uv_totals(
    db: Session, start_utc: datetime, end_utc: datetime
) -> tuple[int, int]:
    if end_utc <= start_utc:
        return 0, 0
    stmt = select(
        func.count(func.distinct(TrafficVisitorDaily.visitor_hash)),
        func.count(func.distinct(TrafficVisitorDaily.day_start_utc)),
    ).where(
        TrafficVisitorDaily.day_start_utc >= start_utc,
        TrafficVisitorDaily.day_start_utc < end_utc,
    )
    row = db.execute(stmt).one()
    return int(row[0] or 0), int(row[1] or 0)


def _serialize_anomaly(row: TrafficAnomalySource) -> dict[str, Any]:
    return {
        "ip": row.ip,
        "hits": int(row.hits or 0),
        "reason": row.reason or "",
        "sample_path": row.sample_path or "",
        "sample_user_agent": row.sample_user_agent or "",
        "first_seen": format_site_time(row.first_seen, "%Y-%m-%d %H:%M:%S"),
        "last_seen": format_site_time(row.last_seen, "%Y-%m-%d %H:%M:%S"),
        "last_seen_iso": row.last_seen.isoformat() if row.last_seen else "",
    }


def _fetch_anomalies(db: Session, now_utc: datetime, *, hours: float = 24) -> dict[str, Any]:
    cutoff = now_utc - timedelta(hours=hours)
    stmt = (
        select(TrafficAnomalySource)
        .where(TrafficAnomalySource.last_seen >= cutoff)
        .order_by(
            TrafficAnomalySource.hits.desc(),
            TrafficAnomalySource.last_seen.desc(),
        )
        .limit(20)
    )
    rows = list(db.execute(stmt).scalars().all())
    total = int(
        db.execute(
            select(func.count(TrafficAnomalySource.id)).where(
                TrafficAnomalySource.last_seen >= cutoff
            )
        ).scalar_one()
        or 0
    )
    return {"items": [_serialize_anomaly(row) for row in rows], "total": total}


def _live_minutes(
    db: Session,
    now_utc: datetime,
    *,
    live_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    current_minute = now_utc.replace(second=0, microsecond=0)
    start_minute = current_minute - timedelta(minutes=59)
    rows = _fetch_minute_rows(db, start_minute, current_minute + timedelta(minutes=1))
    values: dict[datetime, int] = {
        row.bucket_start.replace(second=0, microsecond=0): int(row.requests or 0)
        for row in rows
    }
    if live_snapshot:
        values[current_minute] = max(
            values.get(current_minute, 0),
            int(live_snapshot.get("current_minute_requests", 0) or 0),
        )
    points = []
    for offset in range(60):
        bucket = start_minute + timedelta(minutes=offset)
        points.append(
            {
                "label": format_site_time(bucket, "%H:%M"),
                "requests": int(values.get(bucket, 0)),
            }
        )
    max_requests = max((item["requests"] for item in points), default=0) or 1
    for item in points:
        item["pct"] = round(item["requests"] * 100.0 / max_requests, 2)
    return points


def _build_burst(
    db: Session,
    now_utc: datetime,
    *,
    live_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    points = _live_minutes(db, now_utc, live_snapshot=live_snapshot)
    current_rpm = points[-1]["requests"] if points else 0
    baseline_values = [item["requests"] for item in points[:-1]]
    baseline_rpm = round(sum(baseline_values) / len(baseline_values), 2) if baseline_values else 0.0
    ratio = round(current_rpm / baseline_rpm, 2) if baseline_rpm > 0 else 0.0

    recent_start = now_utc - timedelta(minutes=60)
    rows = _fetch_minute_rows(db, recent_start, now_utc + timedelta(minutes=1))
    db_peak_concurrency = max((int(row.peak_concurrency or 0) for row in rows), default=0)
    live_peak = int((live_snapshot or {}).get("peak_concurrency_current_minute", 0) or 0)
    peak_concurrency = max(db_peak_concurrency, live_peak)

    burst = (
        (current_rpm >= 30 and ratio >= 3)
        or current_rpm >= 120
        or peak_concurrency >= 20
    )
    if burst:
        burst_label = "检测到突发流量"
    elif current_rpm >= 30:
        burst_label = "流量高于平时"
    else:
        burst_label = "流量平稳"

    return {
        "minutes": points,
        "current_rpm": current_rpm,
        "baseline_rpm": baseline_rpm,
        "ratio": ratio,
        "peak_concurrency": peak_concurrency,
        "burst": burst,
        "burst_label": burst_label,
        "active_concurrency": int((live_snapshot or {}).get("active_concurrency", 0) or 0),
        "dropped_events": int((live_snapshot or {}).get("dropped_events", 0) or 0),
        "last_flush_at": format_site_time(
            (live_snapshot or {}).get("last_flush_at"), "%Y-%m-%d %H:%M:%S"
        ),
        "last_flush_error": str((live_snapshot or {}).get("last_flush_error") or ""),
    }


def _build_capacity(db: Session, now_utc: datetime) -> dict[str, Any]:
    cutoff = now_utc - timedelta(hours=48)
    rows = _fetch_minute_rows(db, cutoff, now_utc + timedelta(minutes=1))
    total_requests = sum(int(row.requests or 0) for row in rows)
    total_4xx = sum(int(row.status_4xx or 0) for row in rows)
    total_5xx = sum(int(row.status_5xx or 0) for row in rows)
    duration_sum = sum(int(row.duration_ms_sum or 0) for row in rows)
    peak_rpm = max((int(row.requests or 0) for row in rows), default=0)
    peak_concurrency = max((int(row.peak_concurrency or 0) for row in rows), default=0)

    pool = db_manager.get_pool_status() or {}
    timeout_count = int(pool.get("timeout_count", 0) or 0)
    five_xx_ratio = (total_5xx / total_requests) if total_requests > 0 else 0.0
    four_xx_ratio = (total_4xx / total_requests) if total_requests > 0 else 0.0
    avg_duration = round(duration_sum / total_requests, 1) if total_requests > 0 else 0.0

    reasons: list[str] = []
    if peak_rpm >= _CAPACITY_THRESHOLDS["peak_rpm_migrate"]:
        reasons.append(f"峰值请求达到 {peak_rpm} 次/分钟（阈值 {_CAPACITY_THRESHOLDS['peak_rpm_migrate']}）")
    if peak_concurrency >= _CAPACITY_THRESHOLDS["peak_concurrency_migrate"]:
        reasons.append(
            f"峰值并发达到 {peak_concurrency}（阈值 {_CAPACITY_THRESHOLDS['peak_concurrency_migrate']}）"
        )
    if timeout_count > 0:
        reasons.append(f"数据库连接池等待超时 {timeout_count} 次")
    if total_requests >= 20 and five_xx_ratio > _CAPACITY_THRESHOLDS["five_xx_ratio_migrate"]:
        reasons.append(f"5xx 比例 {five_xx_ratio * 100:.2f}%（阈值 1%）")

    watch_reasons: list[str] = []
    if peak_rpm >= _CAPACITY_THRESHOLDS["peak_rpm_watch"]:
        watch_reasons.append(
            f"峰值请求 {peak_rpm} 次/分钟（关注阈值 {_CAPACITY_THRESHOLDS['peak_rpm_watch']}）"
        )
    if peak_concurrency >= _CAPACITY_THRESHOLDS["peak_concurrency_watch"]:
        watch_reasons.append(
            f"峰值并发 {peak_concurrency}（关注阈值 {_CAPACITY_THRESHOLDS['peak_concurrency_watch']}）"
        )
    if total_requests >= 20 and four_xx_ratio > _CAPACITY_THRESHOLDS["four_xx_ratio_watch"]:
        watch_reasons.append(f"4xx 比例 {four_xx_ratio * 100:.2f}%（关注阈值 10%）")

    if reasons:
        verdict = "migrate"
        verdict_label = "建议迁移 PostgreSQL"
        summary = "；".join(reasons)
    elif watch_reasons:
        verdict = "watch"
        verdict_label = "接近 SQLite 舒适区"
        summary = "；".join(watch_reasons)
    else:
        verdict = "ok"
        verdict_label = "当前容量足够"
        summary = "近 48 小时未触发迁移阈值"

    try:
        dialect_name = str(db.get_bind().dialect.name or "sqlite").lower()
    except Exception:
        dialect_name = "sqlite"

    return {
        "verdict": verdict,
        "verdict_label": verdict_label,
        "summary": summary,
        "reasons": reasons,
        "watch_reasons": watch_reasons,
        "metrics": {
            "peak_rpm": peak_rpm,
            "peak_concurrency": peak_concurrency,
            "requests_48h": total_requests,
            "avg_duration_ms": avg_duration,
            "status_4xx_ratio": round(four_xx_ratio * 100, 2),
            "status_5xx_ratio": round(five_xx_ratio * 100, 2),
            "pool_size": int(pool.get("size", 0) or 0),
            "pool_checked_out": int(pool.get("checked_out", 0) or 0),
            "pool_timeout_count": timeout_count,
            "dialect": dialect_name,
        },
    }


def _safe_call(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _compare(current: int | float, previous: int | float) -> float | None:
    current_value = float(current or 0)
    previous_value = float(previous or 0)
    if previous_value <= 0:
        return None
    return round((current_value - previous_value) * 100.0 / previous_value, 1)


def _composition(
    totals: dict[str, Any],
) -> list[dict[str, Any]]:
    requests = int(totals.get("requests", 0) or 0)
    items = []
    for field, label in COMPOSITION_LABELS.items():
        count = int(totals.get(field, 0) or 0)
        items.append(
            {
                "field": field,
                "label": label,
                "count": count,
                "pct": round(count * 100.0 / requests, 2) if requests else 0.0,
            }
        )
    return items


def get_analytics_summary(
    db: Session,
    range_key: str | None,
    start: str | None = None,
    end: str | None = None,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """页面与 JSON 共用的统计摘要。"""
    current_utc = now_utc or utc_now_naive()
    period = build_period(range_key, start, end, now_utc=current_utc)
    from ..core import traffic_analytics

    live_snapshot = traffic_analytics.get_live_snapshot(current_utc)

    rows = _safe_call(
        lambda: _fetch_hour_rows(db, period.start_utc, period.data_end_utc), []
    )
    totals = _with_ratios(_sum_hour_rows(rows))

    previous_rows = _safe_call(
        lambda: _fetch_hour_rows(db, period.previous_start_utc, period.previous_end_utc), []
    )
    previous_totals = _with_ratios(_sum_hour_rows(previous_rows))

    uv, uv_coverage_days = _safe_call(
        lambda: _uv_totals(db, period.start_utc, period.data_end_utc), (0, 0)
    )
    totals["uv"] = uv
    previous_uv, _ = _safe_call(
        lambda: _uv_totals(db, period.previous_start_utc, period.previous_end_utc), (0, 0)
    )
    previous_totals["uv"] = previous_uv

    trend = _safe_call(
        lambda: _build_trend(rows, period, data_end_utc=period.data_end_utc), []
    )
    # 维度同时存在回源与上报两套：上报更多时改用上报维度，
    # 否则保留更完整的回源维度，避免两套数据相加造成重复计数。
    page_views = int(totals.get("page_views", 0) or 0)
    beacon_page_views = int(totals.get("beacon_page_views", 0) or 0)
    dimension_prefix = (
        "beacon_" if beacon_page_views > 0 and beacon_page_views >= page_views else ""
    )
    paths = _safe_call(
        lambda: _dimension_totals(
            db, period.start_utc, period.data_end_utc, f"{dimension_prefix}path", limit=15
        ),
        [],
    )
    referers = _safe_call(
        lambda: _dimension_totals(
            db, period.start_utc, period.data_end_utc, f"{dimension_prefix}referer", limit=15
        ),
        [],
    )
    source_types_raw = _safe_call(
        lambda: _dimension_totals(
            db, period.start_utc, period.data_end_utc, f"{dimension_prefix}source_type"
        ),
        [],
    )
    utm_sources = _safe_call(
        lambda: _dimension_totals(
            db, period.start_utc, period.data_end_utc, f"{dimension_prefix}utm_source", limit=15
        ),
        [],
    )
    bots = _safe_call(
        lambda: _dimension_totals(db, period.start_utc, period.data_end_utc, "bot", limit=15),
        [],
    )
    statuses = _safe_call(
        lambda: _dimension_totals(db, period.start_utc, period.data_end_utc, "status", limit=20),
        [],
    )
    anomalies = _safe_call(
        lambda: _fetch_anomalies(db, current_utc, hours=24),
        {"items": [], "total": 0},
    )
    burst = _safe_call(
        lambda: _build_burst(db, current_utc, live_snapshot=live_snapshot), _EMPTY_BURST
    )
    capacity = _safe_call(lambda: _build_capacity(db, current_utc), _EMPTY_CAPACITY)

    source_types = [
        {
            "value": item["value"],
            "label": SOURCE_TYPE_LABELS.get(item["value"], item["value"]),
            "hits": item["hits"],
        }
        for item in source_types_raw
    ]

    return {
        "range": {
            "key": period.range_key,
            "label": period.label,
            "granularity": period.granularity,
            "start": period.display_start,
            "end": period.display_end,
            "custom_start": period.custom_start,
            "custom_end": period.custom_end,
            "compare_label": "上一周期",
        },
        "totals": totals,
        "previous": previous_totals,
        "compare": {
            "requests": _compare(totals["requests"], previous_totals["requests"]),
            "page_views": _compare(
                totals["effective_page_views"], previous_totals["effective_page_views"]
            ),
            "uv": _compare(totals["uv"], previous_totals["uv"]),
            "bot_ratio": _compare(totals["bot_ratio"], previous_totals["bot_ratio"]),
        },
        "trend": trend,
        "composition": _composition(totals),
        "paths": [
            {
                "value": "（已折叠的其他路径）" if item["value"] == "__overflow__" else item["value"],
                "hits": item["hits"],
            }
            for item in paths
        ],
        "referers": [
            {
                "value": item["value"],
                "hits": item["hits"],
            }
            for item in referers
        ],
        "source_types": source_types,
        "utm_sources": utm_sources,
        "bots": [
            {
                "value": "（已折叠的其他爬虫）" if item["value"] == "__overflow__" else item["value"],
                "hits": item["hits"],
            }
            for item in bots
        ],
        "statuses": statuses,
        "anomalies": anomalies,
        "burst": burst,
        "capacity": capacity,
        "uv_coverage_days": uv_coverage_days,
        "live": {
            "enabled": bool(live_snapshot.get("enabled", True)),
            "uv_approximate": bool(live_snapshot.get("uv_approximate", False)),
        },
        "notes": [
            "有效访问取回源页面访问与前端 sendBeacon 上报的较大值：上报可覆盖 CDN / 反向代理缓存命中的浏览，回源 PV 则兜住未执行 JS 或被拦截的访问。",
            "回源请求数、爬虫、可疑来源与容量指标只能观察到达源站的流量；CDN 边缘拦截或纯缓存命中不会回源。",
            "UV 按保留窗口内的访客哈希去重，不能把每日 UV 直接相加。",
            "爬虫与可疑来源基于 UA 与路径启发式识别，仅用于观察，不自动封禁。",
            "异常来源 IP 原文最多保留 7 天，正常访客不会落库原始 IP。",
            "CDN / 反向代理直接回源到应用时，必须把回源 IP 加入 TRUSTED_PROXIES；若前面有 Nginx 已还原真实 IP，则保持默认并只信任本机 Nginx，否则 UV 与上报限流会按边缘节点 IP 计算。",
        ],
    }


def get_dashboard_summary(
    db: Session,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """仪表盘摘要：今日 PV/UV、爬虫占比、当前分钟与最近 60 分钟。"""
    current_utc = now_utc or utc_now_naive()
    period = build_period("today", now_utc=current_utc)
    from ..core import traffic_analytics

    live_snapshot = traffic_analytics.get_live_snapshot(current_utc)
    rows = _safe_call(
        lambda: _fetch_hour_rows(db, period.start_utc, period.data_end_utc), []
    )
    totals = _with_ratios(_sum_hour_rows(rows))
    uv, _ = _safe_call(
        lambda: _uv_totals(db, period.start_utc, period.data_end_utc), (0, 0)
    )
    totals["uv"] = uv
    burst = _safe_call(
        lambda: _build_burst(db, current_utc, live_snapshot=live_snapshot), _EMPTY_BURST
    )
    anomalies = _safe_call(
        lambda: _fetch_anomalies(db, current_utc, hours=24),
        {"items": [], "total": 0},
    )
    capacity = _safe_call(lambda: _build_capacity(db, current_utc), _EMPTY_CAPACITY)

    has_data = bool(
        totals.get("requests")
        or totals.get("page_views")
        or totals.get("beacon_page_views")
        or uv
    )
    return {
        "has_data": has_data,
        "totals": totals,
        "burst": burst,
        "anomaly_total": int(anomalies.get("total", 0) or 0),
        "capacity": capacity,
        "enabled": bool(live_snapshot.get("enabled", True)),
    }


def get_live_fragment(
    db: Session,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """实时片段：最近 60 分钟、突发倍率、异常来源与容量结论。"""
    current_utc = now_utc or utc_now_naive()
    from ..core import traffic_analytics

    live_snapshot = traffic_analytics.get_live_snapshot(current_utc)
    burst = _safe_call(
        lambda: _build_burst(db, current_utc, live_snapshot=live_snapshot), _EMPTY_BURST
    )
    anomalies = _safe_call(
        lambda: _fetch_anomalies(db, current_utc, hours=0.25),
        {"items": [], "total": 0},
    )
    capacity = _safe_call(lambda: _build_capacity(db, current_utc), _EMPTY_CAPACITY)
    return {
        "burst": burst,
        "anomalies": anomalies,
        "capacity": capacity,
        "updated_at": site_now().strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": bool(live_snapshot.get("enabled", True)),
    }
