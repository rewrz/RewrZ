"""统一时间工具：数据库统一存储无时区的 UTC 时间，展示时按站点时区转换。"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import DEFAULT_SITE_TIMEZONE, settings


def utc_now_naive() -> datetime:
    """返回无时区的 UTC 时间，保持数据库 DateTime 字段的存储语义。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


def get_site_timezone() -> ZoneInfo:
    """获取站点展示时区，配置非法时回落到默认时区。"""
    name = str(getattr(settings, "SITE_TIMEZONE", "") or "").strip() or DEFAULT_SITE_TIMEZONE
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_SITE_TIMEZONE)


def site_now() -> datetime:
    """返回带站点时区的当前时间。"""
    return datetime.now(get_site_timezone())


def site_now_naive() -> datetime:
    """返回无时区的站点本地时间，仅用于标题、文件名等展示场景。"""
    return site_now().replace(tzinfo=None)


def to_site_time(dt: datetime | None) -> datetime | None:
    """把无时区 UTC（或带时区时间）转换为站点时区的带时区时间。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_site_timezone())


def format_site_time(dt: datetime | None, format_string: str) -> str:
    """按站点时区格式化时间。"""
    localized = to_site_time(dt)
    if localized is None:
        return ""
    return localized.strftime(format_string)


def as_utc(dt: datetime | None) -> datetime | None:
    """把无时区 UTC（或带时区时间）转换为带 UTC 时区的时间。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def site_local_to_utc_naive(dt: datetime | None) -> datetime | None:
    """把无时区的站点本地时间转换为数据库使用的无时区 UTC 时间。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_site_timezone())
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: datetime | None) -> str:
    """输出带 Z 的 UTC ISO 时间，供接口与 RSS 使用。"""
    aware = as_utc(dt)
    if aware is None:
        return ""
    return aware.isoformat().replace("+00:00", "Z")


def site_month_range_utc(year: int, month: int) -> tuple[datetime, datetime]:
    """把站点时区的自然月转换为数据库使用的无时区 UTC 起止区间。"""
    site_tz = get_site_timezone()
    start_local = datetime(year, month, 1, tzinfo=site_tz)
    next_year = year + 1 if month == 12 else year
    next_month = 1 if month == 12 else month + 1
    end_local = datetime(next_year, next_month, 1, tzinfo=site_tz)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def site_day_start_utc(dt: datetime | None = None) -> datetime:
    """返回站点自然日 00:00 对应的无时区 UTC 时间，作为统计日键。

    例如 Asia/Shanghai 的 2026-10-24 返回 2026-10-23 16:00:00。
    统计表统一存这个值，查询时再按站点时区还原为自然日。
    """
    if dt is None:
        site_dt = site_now()
    else:
        site_dt = to_site_time(dt) or site_now()
    local_midnight = site_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
