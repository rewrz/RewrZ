from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from ..core.time_utils import utc_now_naive
from .base import Base

class Comment(Base):
    __tablename__ = "comments"
    # 评论列表按“文章 + 状态 + 时间”过滤/排序，回复树按 parent_id 查找子级；
    # 这两个索引直接影响详情页评论加载与后台审核列表的查询成本。
    __table_args__ = (
        Index("ix_comments_post_status_created", "post_id", "status", "created_at"),
        Index("ix_comments_parent_id", "parent_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    author_name = Column(String, nullable=False)
    author_email = Column(String, nullable=False)
    author_url = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending") # 'approved', 'pending', 'spam'
    is_admin_reply = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now_naive)

    post = relationship("Post", back_populates="comments")
    parent = relationship("Comment", remote_side=[id])
    children = relationship("Comment", back_populates="parent")
