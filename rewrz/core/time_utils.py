"""统一时间工具，避免使用已弃用的无时区 UTC 接口。"""

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """返回无时区的 UTC 时间，保持现有数据库 DateTime 字段的存储语义。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
