"""
用户模型

定义系统用户的数据结构，包括管理员和博主账户。
支持自定义头像上传和管理功能。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from .base import Base

class User(Base):
    """用户模型类"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    email = Column(String, unique=True, index=True)
    role = Column(String, default="admin") # 未来的多用户角色系统
    
    # 头像相关字段
    avatar_url = Column(String, nullable=True) # 自定义头像 URL
    avatar_filename = Column(String, nullable=True) # 头像文件名
    use_gravatar = Column(String, default="auto") # gravatar使用设置：auto/enabled/disabled
    
    # 用户信息字段
    display_name = Column(String, nullable=True) # 显示名称
    bio = Column(Text, nullable=True) # 个人简介
    website = Column(String, nullable=True) # 个人网站
    
    # 时间戳字段
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime, nullable=True) # 最后登录时间
