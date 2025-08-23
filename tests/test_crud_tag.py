import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.tag import Tag
from rewrz.schemas.tag import TagCreate, TagUpdate
from rewrz.crud import tag as crud_tag

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

def test_create_tag(db: Session):
    tag_data = TagCreate(name="Test Tag", slug="test-tag")
    tag = crud_tag.create_tag(db, tag_data)
    assert tag.name == "Test Tag"
    assert tag.slug == "test-tag"

def test_get_tag(db: Session):
    tag_data = TagCreate(name="Fetch Tag", slug="fetch-tag")
    created_tag = crud_tag.create_tag(db, tag_data)
    
    fetched_tag = crud_tag.get_tag(db, tag_id=created_tag.id)
    assert fetched_tag.id == created_tag.id
    assert fetched_tag.name == "Fetch Tag"

def test_get_tag_by_slug(db: Session):
    tag_data = TagCreate(name="Slug Tag", slug="slug-tag")
    crud_tag.create_tag(db, tag_data)
    
    fetched_tag = crud_tag.get_tag_by_slug(db, slug="slug-tag")
    assert fetched_tag.slug == "slug-tag"

def test_get_tags(db: Session):
    crud_tag.create_tag(db, TagCreate(name="Tag1", slug="tag1"))
    crud_tag.create_tag(db, TagCreate(name="Tag2", slug="tag2"))
    
    tags = crud_tag.get_tags(db)
    assert len(tags) == 2

def test_update_tag(db: Session):
    tag_data = TagCreate(name="Original Tag", slug="original-tag")
    created_tag = crud_tag.create_tag(db, tag_data)

    update_data = TagUpdate(name="Updated Tag", slug="updated-tag")
    updated_tag = crud_tag.update_tag(db, tag_id=created_tag.id, tag_update=update_data)
    assert updated_tag.name == "Updated Tag"
    assert updated_tag.slug == "updated-tag"

def test_delete_tag(db: Session):
    tag_data = TagCreate(name="Delete Me", slug="delete-me")
    created_tag = crud_tag.create_tag(db, tag_data)

    deleted_tag = crud_tag.delete_tag(db, tag_id=created_tag.id)
    assert deleted_tag.id == created_tag.id
    assert crud_tag.get_tag(db, tag_id=created_tag.id) is None
