from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Comment(Base):
    __tablename__ = "comments"

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
    created_at = Column(DateTime, default=func.now())

    post = relationship("Post")
    parent = relationship("Comment", remote_side=[id])
