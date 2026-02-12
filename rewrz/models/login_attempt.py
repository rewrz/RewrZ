"""
后台登录审计模型

用于记录后台登录尝试（成功/失败）以支持：
1. 登录审计日志
2. IP 失败次数统计与封禁判断
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=False, index=True)
    user_agent = Column(Text, nullable=True)
    success = Column(Boolean, nullable=False, default=False, index=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
