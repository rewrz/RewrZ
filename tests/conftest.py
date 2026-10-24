"""
测试配置文件。

默认使用 pytest 临时目录中的独立 SQLite 文件，避免多个测试进程共享
`tests/test.db` 触发锁冲突。
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz.core.cache import clear_cache
from rewrz.core.database import Base


@pytest.fixture(scope="session")
def test_engine(tmp_path_factory):
    """创建测试数据库引擎。"""
    temp_dir = tmp_path_factory.mktemp("sqlite-test-db")
    db_path = Path(temp_dir) / f"session-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """创建测试数据库会话。"""
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clear_setting_cache_between_tests():
    """清理全局设置缓存，避免不同测试数据库之间串值。"""
    from rewrz.core.public_list_cache import clear_public_list_cache
    from rewrz.core.public_metrics_cache import clear_public_metrics_memory_cache
    from rewrz.core import traffic_analytics
    from rewrz.api import analytics as analytics_api

    traffic_analytics.reset_for_tests()
    analytics_api.clear_caches()
    clear_cache()
    clear_public_metrics_memory_cache()
    clear_public_list_cache()
    yield
    traffic_analytics.reset_for_tests()
    analytics_api.clear_caches()
    clear_cache()
    clear_public_metrics_memory_cache()
    clear_public_list_cache()


@pytest.fixture(autouse=True)
def restore_dynamic_settings_between_tests():
    """部分测试会触发 reload_config，需还原全局配置避免跨用例串扰。"""
    from rewrz.core.config import settings

    snapshot = dict(vars(settings))
    yield
    for key in [key for key in vars(settings) if key not in snapshot]:
        delattr(settings, key)
    for key, value in snapshot.items():
        setattr(settings, key, value)


def get_db_session():
    """
    获取数据库会话的便捷函数。

    该辅助函数仅用于需要临时直接创建测试连接的场景，不复用固定文件库。
    """
    engine = create_engine(
        f"sqlite:///./tests/.tmp-{uuid4().hex}.db",
        connect_args={"check_same_thread": False},
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_local()
