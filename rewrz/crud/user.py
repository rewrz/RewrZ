"""用户CRUD操作模块

本模块提供用户相关的数据库操作功能，包括创建、读取、更新、删除用户信息。
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models import User
from ..schemas import UserCreate, UserUpdate

def get_user(db: Session, user_id: int):
    """根据用户ID获取用户信息"""
    return db.execute(select(User).filter(User.id == user_id)).scalar_one_or_none()

def get_user_by_username(db: Session, username: str):
    """根据用户名获取用户信息"""
    return db.execute(select(User).filter(User.username == username)).scalar_one_or_none()

def get_user_by_email(db: Session, email: str):
    """根据邮箱地址获取用户信息"""
    return db.execute(select(User).filter(User.email == email)).scalar_one_or_none()

from ..core.security import get_password_hash

def create_user(db: Session, user: UserCreate):
    """创建新用户
    
    Args:
        db: 数据库会话
        user: 用户创建数据
        
    Returns:
        创建的用户对象
    """
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: UserUpdate):
    """更新用户信息
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        user_update: 用户更新数据
        
    Returns:
        更新后的用户对象
    """
    db_user = get_user(db, user_id)
    if db_user:
        update_data = user_update.model_dump(exclude_unset=True)
        # 如果包含密码字段，需要重新哈希
        if 'password' in update_data and update_data['password']:
            hashed_password = get_password_hash(update_data.pop('password'))
            db_user.hashed_password = hashed_password
        
        for key, value in update_data.items():
            setattr(db_user, key, value)
        
        db.commit()
        db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    """删除用户
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        
    Returns:
        被删除的用户对象
    """
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user
