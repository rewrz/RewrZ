from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, Dict, Any
from ..models import Setting
from ..schemas import SettingCreate, SettingUpdate
from ..core.cache import cache_settings, clear_cache, cache_key_for_setting, cache # Import cache functions

def get_setting(db: Session, key: str) -> Optional[Setting]:
    cache_key = cache_key_for_setting(key)
    if cache_key in cache:
        cached_data = cache[cache_key]
        if cached_data is None:
            return None
        # Reconstruct the Setting object from the cached dictionary
        return Setting(**cached_data)

    result = db.execute(select(Setting).filter(Setting.key == key)).scalar_one_or_none()

    if result:
        # Cache the dictionary representation of the object
        cached_data = {c.name: getattr(result, c.name) for c in result.__table__.columns}
        cache[cache_key] = cached_data
    # Don't cache None values to avoid confusion in tests

    return result

def create_setting(db: Session, setting: SettingCreate) -> Setting:
    db_setting = Setting(key=setting.key, value=setting.value, description=setting.description)
    db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    # Clear cache for this setting after creation
    clear_cache(cache_key_for_setting(setting.key))
    return db_setting

def update_setting(db: Session, key: str, setting_update: SettingUpdate) -> Optional[Setting]:
    db_setting = db.execute(select(Setting).filter(Setting.key == key)).scalar_one_or_none()
    if db_setting:
        for field, value in setting_update.model_dump(exclude_unset=True).items():
            setattr(db_setting, field, value)
        db.commit()
        db.refresh(db_setting)
        # Clear cache for this setting after update
        clear_cache(cache_key_for_setting(key))
    return db_setting

def delete_setting(db: Session, key: str) -> Optional[Setting]:
    db_setting = db.execute(select(Setting).filter(Setting.key == key)).scalar_one_or_none()
    if db_setting:
        db.delete(db_setting)
        db.commit()
        # Remove from cache instead of clearing to None
        cache_key = cache_key_for_setting(key)
        if cache_key in cache:
            del cache[cache_key]
        clear_cache(cache_key_for_setting(key))
    return db_setting


def get_settings_by_category(db: Session, category: str) -> list[Setting]:
    """按分类获取设置列表"""
    result = db.execute(select(Setting).filter(Setting.category == category)).scalars().all()
    return list(result)


def get_all_settings(db: Session) -> list[Setting]:
    """获取所有设置"""
    result = db.execute(select(Setting)).scalars().all()
    return list(result)


def get_public_contact_email(db: Session) -> Optional[str]:
    """
    获取公开联系邮箱地址
    
    Args:
        db: 数据库会话
        
    Returns:
        Optional[str]: 公开联系邮箱地址，如果未设置则返回None
    """
    setting = get_setting(db, "public_contact_email")
    if setting and setting.value:
        return setting.value.get("value")
    return None