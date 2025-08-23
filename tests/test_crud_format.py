import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.format import Format
from rewrz.schemas.format import FormatCreate, FormatUpdate
from rewrz.crud import format as crud_format

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./tests/test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after tests

def test_create_format(db: Session):
    format_data = FormatCreate(name="测试格式", slug="test-format")
    format = crud_format.create_format(db, format_data)
    assert format.name == "测试格式"
    assert format.slug == "test-format"

def test_get_format(db: Session):
    format_data = FormatCreate(name="获取格式", slug="fetch-format")
    created_format = crud_format.create_format(db, format_data)
    
    fetched_format = crud_format.get_format(db, format_id=created_format.id)
    assert fetched_format.id == created_format.id
    assert fetched_format.name == "获取格式"

def test_get_format_by_slug(db: Session):
    format_data = FormatCreate(name="Slug格式", slug="slug-format")
    created_format = crud_format.create_format(db, format_data)
    
    fetched_format = crud_format.get_format_by_slug(db, slug="slug-format")
    assert fetched_format.slug == "slug-format"

def test_get_formats(db: Session):
    crud_format.create_format(db, FormatCreate(name="格式1", slug="format1"))
    crud_format.create_format(db, FormatCreate(name="格式2", slug="format2"))
    
    formats = crud_format.get_formats(db)
    assert len(formats) >= 2  # May include default formats from migration

def test_update_format(db: Session):
    format_data = FormatCreate(name="原始格式", slug="original-format")
    created_format = crud_format.create_format(db, format_data)

    update_data = FormatUpdate(name="更新格式", slug="updated-format")
    updated_format = crud_format.update_format(db, format_id=created_format.id, format_update=update_data)
    assert updated_format.name == "更新格式"
    assert updated_format.slug == "updated-format"

def test_delete_format(db: Session):
    format_data = FormatCreate(name="删除我", slug="delete-me")
    created_format = crud_format.create_format(db, format_data)

    deleted_format = crud_format.delete_format(db, format_id=created_format.id)
    assert deleted_format.id == created_format.id
    assert crud_format.get_format(db, format_id=created_format.id) is None

def test_format_slug_auto_generation(db: Session):
    format_data = FormatCreate(name="自动生成 Slug", slug="")
    format = crud_format.create_format(db, format_data)
    # The slug should be auto-generated from the name
    assert format.slug == "zi-dong-sheng-cheng-slug"  # Based on slugify function