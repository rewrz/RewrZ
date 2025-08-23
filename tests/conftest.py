"""
测试配置文件

提供测试所需的fixture和配置。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rewrz.core.database import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.category import Category
from rewrz.models.tag import Tag
from rewrz.models.comment import Comment
from rewrz.models.setting import Setting
from rewrz.models.format import Format


# 测试数据库URL
TEST_DATABASE_URL = "sqlite:///./tests/test.db"


@pytest.fixture(scope="session")
def test_engine():
    """创建测试数据库引擎"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db(test_engine):
    """创建测试数据库会话"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """获取数据库会话的便捷函数"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()