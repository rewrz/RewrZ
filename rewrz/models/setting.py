"""
设置模型

用于存储系统配置项，包括反垃圾设置、主题设置等。
支持分类管理和类型标识。
"""
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from .base import Base

class Setting(Base):
    """设置模型类"""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=False) # 以JSON格式存储设置值
    description = Column(Text, nullable=True) # 设置描述
    category = Column(String, nullable=True, index=True) # 设置分类
    type = Column(String, nullable=True) # 设置类型（string, integer, boolean, array）
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
