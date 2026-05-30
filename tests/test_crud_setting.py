from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rewrz.core.cache import cache, cache_key_for_setting, clear_cache
from rewrz.crud import setting as crud_setting
from rewrz.models.base import Base
from rewrz.models.setting import Setting
from rewrz.schemas.setting import SettingCreate, SettingUpdate


@pytest.fixture(name="db")
def session_fixture(tmp_path):
    db_path = tmp_path / f"crud-setting-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()

@pytest.fixture(autouse=True)
def clear_all_cache_after_each_test():
    """Fixture to clear the entire cache before each test."""
    clear_cache()
    yield
    clear_cache()

def test_create_setting(db: Session):
    setting_data = SettingCreate(key="test_key", value={"value": "test_value"}, description="A test setting")
    setting = crud_setting.create_setting(db, setting_data)
    assert setting.key == "test_key"
    assert setting.value == {"value": "test_value"}
    assert setting.description == "A test setting"
    assert cache_key_for_setting("test_key") not in cache # Cache should be cleared after creation

def test_get_setting_and_cache(db: Session):
    setting_data = SettingCreate(key="cached_key", value={"value": "initial_value"})
    crud_setting.create_setting(db, setting_data)

    # First call should fetch from DB and cache
    setting1 = crud_setting.get_setting(db, "cached_key")
    assert setting1.value == {"value": "initial_value"}
    assert cache_key_for_setting("cached_key") in cache

    # Modify the setting directly in DB (bypassing crud_setting.update_setting)
    # This simulates an external change to verify cache is used
    db_setting = db.query(Setting).filter(Setting.key == "cached_key").first()
    db_setting.value = {"value": "modified_value_in_db"}
    db.commit()

    # Second call should return cached value, not the modified DB value
    setting2 = crud_setting.get_setting(db, "cached_key")
    assert setting2.value == {"value": "initial_value"} # Still the cached value

    # Now, clear the cache for this specific key
    clear_cache(cache_key_for_setting("cached_key"))
    assert cache_key_for_setting("cached_key") not in cache

    # Third call should fetch from DB and cache the new value
    setting3 = crud_setting.get_setting(db, "cached_key")
    assert setting3.value == {"value": "modified_value_in_db"} # Now it should be the updated DB value
    assert cache_key_for_setting("cached_key") in cache

def test_update_setting_clears_cache(db: Session):
    setting_data = SettingCreate(key="update_key", value={"value": "old_value"})
    crud_setting.create_setting(db, setting_data)

    # Populate cache
    crud_setting.get_setting(db, "update_key")
    assert cache_key_for_setting("update_key") in cache

    # Update setting
    update_data = SettingUpdate(value={"value": "new_value"})
    updated_setting = crud_setting.update_setting(db, "update_key", update_data)
    assert updated_setting.value == {"value": "new_value"}
    assert cache_key_for_setting("update_key") not in cache # Cache should be cleared

    # Re-fetch to ensure it's from DB
    re_fetched_setting = crud_setting.get_setting(db, "update_key")
    assert re_fetched_setting.value == {"value": "new_value"}

def test_delete_setting_clears_cache(db: Session):
    setting_data = SettingCreate(key="delete_key", value={"value": "some_value"})
    crud_setting.create_setting(db, setting_data)

    # Populate cache
    crud_setting.get_setting(db, "delete_key")
    assert cache_key_for_setting("delete_key") in cache

    # Delete setting
    deleted_setting = crud_setting.delete_setting(db, "delete_key")
    assert deleted_setting.key == "delete_key"
    # After deletion, the setting should not be in the database
    assert crud_setting.get_setting(db, "delete_key") is None
    # And the cache for this key should be cleared
    assert cache_key_for_setting("delete_key") not in cache
