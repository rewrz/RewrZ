"""文章浏览量指标模型。

浏览量原先以 `post_views_count_<id>` 的键写进 settings 表，导致配置表被
每篇文章一行撑大，读取侧还得用 LIKE 全表扫描。这里改为独立表：一篇一行，
写入走批量 upsert，读取按主键直取。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer

from ..core.time_utils import utc_now_naive
from .base import Base


class PostViewStat(Base):
    __tablename__ = "post_view_stats"

    post_id = Column(
        Integer,
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    views = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        nullable=False,
    )
