"""访问统计聚合模型

只保存聚合结果，不保存逐条请求日志：
1. traffic_minute_stats：分钟聚合，用于突发检测与容量评估（保留 48 小时）
2. traffic_hour_stats：小时聚合，用于日/周/月/年趋势（保留 3 年）
3. traffic_dimensions_daily：每日 Top N 维度（路径、来源、爬虫、状态码等）
4. traffic_visitors_daily：每日访客哈希，用于 UV 去重
5. traffic_anomaly_sources：异常来源 IP，仅保留 7 天

所有时间字段一律存无时区的 UTC 时间；每日维度的 day_start_utc 存的是
“站点自然日 00:00 对应的 UTC 时间”，例如 Asia/Shanghai 的 2026-10-24
存为 2026-10-23 16:00:00，查询时再按站点时区聚合。
"""
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from ..core.time_utils import utc_now_naive

from .base import Base


class TrafficMinuteStat(Base):
    """分钟聚合（保留 48 小时）"""

    __tablename__ = "traffic_minute_stats"

    bucket_start = Column(DateTime, primary_key=True, nullable=False)
    requests = Column(BigInteger, nullable=False, default=0)
    page_views = Column(BigInteger, nullable=False, default=0)
    beacon_page_views = Column(BigInteger, nullable=False, default=0)
    bot_requests = Column(BigInteger, nullable=False, default=0)
    suspicious_requests = Column(BigInteger, nullable=False, default=0)
    admin_requests = Column(BigInteger, nullable=False, default=0)
    api_requests = Column(BigInteger, nullable=False, default=0)
    htmx_requests = Column(BigInteger, nullable=False, default=0)
    other_requests = Column(BigInteger, nullable=False, default=0)
    status_4xx = Column(BigInteger, nullable=False, default=0)
    status_5xx = Column(BigInteger, nullable=False, default=0)
    duration_ms_sum = Column(BigInteger, nullable=False, default=0)
    peak_concurrency = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class TrafficHourStat(Base):
    """小时聚合（保留 3 年）"""

    __tablename__ = "traffic_hour_stats"

    bucket_start = Column(DateTime, primary_key=True, nullable=False)
    requests = Column(BigInteger, nullable=False, default=0)
    page_views = Column(BigInteger, nullable=False, default=0)
    beacon_page_views = Column(BigInteger, nullable=False, default=0)
    bot_requests = Column(BigInteger, nullable=False, default=0)
    suspicious_requests = Column(BigInteger, nullable=False, default=0)
    admin_requests = Column(BigInteger, nullable=False, default=0)
    api_requests = Column(BigInteger, nullable=False, default=0)
    htmx_requests = Column(BigInteger, nullable=False, default=0)
    other_requests = Column(BigInteger, nullable=False, default=0)
    status_4xx = Column(BigInteger, nullable=False, default=0)
    status_5xx = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class TrafficDimensionDaily(Base):
    """每日 Top N 维度

    kind 取值：path / referer / bot / source_type / utm_source / status，
    以及前端上报专用的 beacon_path / beacon_referer / beacon_source_type / beacon_utm_source
    （上报维度单独存放，避免与回源维度相加造成重复计数）。
    """

    __tablename__ = "traffic_dimensions_daily"
    __table_args__ = (
        UniqueConstraint("day_start_utc", "kind", "value", name="uq_traffic_dimension_daily"),
        Index("ix_traffic_dimensions_daily_day_kind", "day_start_utc", "kind"),
    )

    id = Column(Integer, primary_key=True, index=True)
    day_start_utc = Column(DateTime, nullable=False)
    kind = Column(String(20), nullable=False)
    value = Column(String(512), nullable=False)
    hits = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class TrafficVisitorDaily(Base):
    """每日访客哈希（HMAC-SHA256 截断），用于 UV 去重"""

    __tablename__ = "traffic_visitors_daily"
    __table_args__ = (
        UniqueConstraint("day_start_utc", "visitor_hash", name="uq_traffic_visitor_daily"),
        Index("ix_traffic_visitors_daily_day_start_utc", "day_start_utc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    day_start_utc = Column(DateTime, nullable=False)
    visitor_hash = Column(String(32), nullable=False)
    hits = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class TrafficAnomalySource(Base):
    """异常来源 IP（保留 7 天，最多 500 行）

    只有被判定为可疑的请求才会落原始 IP，正常访客不会入库。
    """

    __tablename__ = "traffic_anomaly_sources"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(45), nullable=False, unique=True, index=True)
    hits = Column(BigInteger, nullable=False, default=0)
    reason = Column(String(100), nullable=False, default="")
    sample_path = Column(String(512), nullable=False, default="")
    sample_user_agent = Column(String(255), nullable=False, default="")
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
