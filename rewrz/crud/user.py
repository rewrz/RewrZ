"""用户 CRUD 操作模块。

本模块提供用户相关的数据库操作功能，包括创建、读取、更新、删除用户信息。
"""
from datetime import datetime

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


def get_users(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
):
    """获取用户列表，可按用户名/邮箱/显示名进行轻量搜索。"""
    stmt = select(User).order_by(User.id.asc()).offset(max(0, int(skip))).limit(max(1, int(limit)))
    search_text = str(search or "").strip()
    if search_text:
        like_text = f"%{search_text}%"
        stmt = (
            select(User)
            .filter(
                (User.username.ilike(like_text))
                | (User.email.ilike(like_text))
                | (User.display_name.ilike(like_text))
            )
            .order_by(User.id.asc())
            .offset(max(0, int(skip)))
            .limit(max(1, int(limit)))
        )
    return db.execute(stmt).scalars().all()

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
    db_user = User(username=user.username, email=user.email, hashed_password=hashed_password, token_version=1)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_admin_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    role: str = "admin",
    is_active: bool = True,
    display_name: str | None = None,
):
    """创建后台用户。"""
    hashed_password = get_password_hash(password)
    db_user = User(
        username=str(username or "").strip(),
        email=str(email or "").strip().lower(),
        hashed_password=hashed_password,
        token_version=1,
        role=str(role or "admin").strip(),
        is_active=bool(is_active),
        display_name=(str(display_name or "").strip() or None),
    )
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


def set_user_active_status(db: Session, user_id: int, *, is_active: bool):
    db_user = get_user(db, user_id)
    if db_user:
        db_user.is_active = bool(is_active)
        db.commit()
        db.refresh(db_user)
    return db_user


def set_user_role(db: Session, user_id: int, *, role: str):
    db_user = get_user(db, user_id)
    if db_user:
        db_user.role = str(role or "").strip()
        db.commit()
        db.refresh(db_user)
    return db_user


def reset_user_password(db: Session, user_id: int, *, password: str):
    db_user = get_user(db, user_id)
    if db_user:
        db_user.hashed_password = get_password_hash(password)
        db.commit()
        db.refresh(db_user)
    return db_user


def set_password_reset_token(
    db: Session,
    user_id: int,
    *,
    token_hash: str,
    sent_at: datetime,
    expires_at: datetime,
):
    """为用户写入一次性找回密码令牌。"""
    db_user = get_user(db, user_id)
    if db_user:
        db_user.password_reset_token_hash = str(token_hash or "").strip() or None
        db_user.password_reset_sent_at = sent_at
        db_user.password_reset_expires_at = expires_at
        db.commit()
        db.refresh(db_user)
    return db_user


def clear_password_reset_token(db: Session, user_id: int):
    """清空用户的找回密码令牌状态。"""
    db_user = get_user(db, user_id)
    if db_user:
        db_user.password_reset_token_hash = None
        db_user.password_reset_sent_at = None
        db_user.password_reset_expires_at = None
        db.commit()
        db.refresh(db_user)
    return db_user


def get_user_by_password_reset_token_hash(db: Session, token_hash: str):
    """根据找回密码令牌哈希查找用户。"""
    normalized_hash = str(token_hash or "").strip()
    if not normalized_hash:
        return None
    return db.execute(select(User).filter(User.password_reset_token_hash == normalized_hash)).scalar_one_or_none()


def force_logout_user(db: Session, user_id: int):
    """递增用户令牌版本，使其现有登录态立即失效。"""
    db_user = get_user(db, user_id)
    if db_user:
        current_version = int(getattr(db_user, "token_version", 1) or 1)
        db_user.token_version = current_version + 1
        db.commit()
        db.refresh(db_user)
    return db_user


def set_user_theme_preference(db: Session, user_id: int, *, theme_preference: str | None):
    """更新用户的主题偏好。"""
    db_user = get_user(db, user_id)
    if db_user:
        normalized_value = str(theme_preference or "").strip() or None
        db_user.theme_preference = normalized_value
        db.commit()
        db.refresh(db_user)
    return db_user
