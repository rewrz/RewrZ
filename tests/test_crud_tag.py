import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.post import Post
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


def test_bulk_delete_tags(db: Session):
    delete_me = crud_tag.create_tag(db, TagCreate(name="Bulk Delete Tag", slug="bulk-delete-tag"))
    used_by_post = crud_tag.create_tag(db, TagCreate(name="Used By Post Tag", slug="used-by-post-tag"))
    delete_me_id = delete_me.id
    used_by_post_id = used_by_post.id

    post = Post(title="Tag Test Post", slug="tag-test-post", content_markdown="x", content_html="<p>x</p>")
    post.tags.append(used_by_post)
    db.add(post)
    db.commit()

    result = crud_tag.bulk_delete_tags(db, [delete_me_id, used_by_post_id, 99999])

    assert result["deleted_ids"] == [delete_me_id]
    assert result["blocked_by_posts_ids"] == [used_by_post_id]
    assert result["missing_ids"] == [99999]
    assert crud_tag.get_tag(db, tag_id=delete_me_id) is None
    assert crud_tag.get_tag(db, tag_id=used_by_post_id) is not None
