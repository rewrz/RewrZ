from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    key_prefix = Column(String(24), nullable=False, unique=True, index=True)
    secret_hash = Column(String(255), nullable=False)
    access_level = Column(String(32), nullable=False, default="read_only", index=True)
    status = Column(String(16), nullable=False, default="active", index=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    created_by = relationship("User")
