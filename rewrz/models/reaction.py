from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, Index
from sqlalchemy.sql import func

from .base import Base


class ContentReaction(Base):
    __tablename__ = "content_reactions"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(16), nullable=False, index=True)  # post / comment
    target_id = Column(Integer, nullable=False, index=True)
    visitor_token = Column(String(96), nullable=False, index=True)
    like_active = Column(Boolean, nullable=False, default=False)
    reaction_type = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "visitor_token", name="uq_content_reaction_target_visitor"),
        Index("idx_content_reaction_target_pair", "target_type", "target_id"),
    )
