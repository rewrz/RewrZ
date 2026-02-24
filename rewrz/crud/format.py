"""格式CRUD操作模块

本模块提供内容格式相关的数据库操作功能，支持多重身份内容系统。
格式包括：标准文章、微博、相册、视频、音乐等。
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from ..models import Format
from ..schemas import FormatCreate, FormatUpdate
from slugify import slugify

def get_format(db: Session, format_id: int) -> Optional[Format]:
    """根据格式ID获取格式信息"""
    return db.execute(select(Format).filter(Format.id == format_id)).scalar_one_or_none()

def get_format_by_slug(db: Session, slug: str) -> Optional[Format]:
    """根据格式别名获取格式信息"""
    return db.execute(select(Format).filter(Format.slug == slug)).scalar_one_or_none()

def get_format_by_name(db: Session, name: str) -> Optional[Format]:
    """根据格式名称获取格式信息"""
    return db.execute(select(Format).filter(Format.name == name)).scalar_one_or_none()

def get_formats(db: Session, skip: int = 0, limit: int = 100) -> List[Format]:
    """获取所有格式列表，支持分页"""
    return db.execute(select(Format).offset(skip).limit(limit)).scalars().all()

def create_format(db: Session, format: FormatCreate, *, auto_commit: bool = True) -> Format:
    """创建新格式
    
    如果未提供别名，则自动从名称生成
    """
    # 仅在未提供别名时自动生成
    slug = format.slug if format.slug else slugify(format.name)
    existing_by_slug = get_format_by_slug(db, slug)
    if existing_by_slug:
        return existing_by_slug

    # 开发阶段强制收敛：同名即视为同一格式，直接更新为当前slug
    existing_by_name = get_format_by_name(db, format.name)
    if existing_by_name:
        if existing_by_name.slug != slug:
            existing_by_name.slug = slug
            if auto_commit:
                db.commit()
                db.refresh(existing_by_name)
            else:
                db.flush()
        return existing_by_name

    db_format = Format(name=format.name, slug=slug)
    db.add(db_format)
    if auto_commit:
        db.commit()
        db.refresh(db_format)
    else:
        db.flush()
    return db_format

def update_format(db: Session, format_id: int, format_update: FormatUpdate) -> Optional[Format]:
    """更新格式信息
    
    如果名称发生变化，会自动更新别名
    """
    db_format = db.execute(select(Format).filter(Format.id == format_id)).scalar_one_or_none()
    if db_format:
        for key, value in format_update.model_dump(exclude_unset=True).items():
            if key == "name":
                # 如果名称变化，自动更新别名
                db_format.slug = slugify(value)
            setattr(db_format, key, value)
        db.commit()
        db.refresh(db_format)
    return db_format

def delete_format(db: Session, format_id: int) -> Optional[Format]:
    """删除格式
    
    Args:
        db: 数据库会话
        format_id: 格式ID
        
    Returns:
        被删除的格式对象
    """
    db_format = db.execute(select(Format).filter(Format.id == format_id)).scalar_one_or_none()
    if db_format:
        db.delete(db_format)
        db.commit()
    return db_format
