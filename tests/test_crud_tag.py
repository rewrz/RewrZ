import unicodedata
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rewrz.crud import tag as crud_tag
from rewrz.models.base import Base
from rewrz.models.post import Post
from rewrz.schemas.tag import TagCreate, TagUpdate


@pytest.fixture(name="db")
def session_fixture(tmp_path):
    db_path = tmp_path / f"crud-tag-{uuid4().hex}.db"
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


def test_resolve_or_create_tag_reuses_existing_tag_by_name_and_slug(db: Session):
    existing = crud_tag.create_tag(db, TagCreate(name="网站", slug="web"))

    assert crud_tag.resolve_or_create_tag(db, "网站").id == existing.id
    assert crud_tag.resolve_or_create_tag(db, "  网站  ").id == existing.id
    assert crud_tag.resolve_or_create_tag(db, "web").id == existing.id
    assert crud_tag.resolve_or_create_tag(db, "WEB").id == existing.id
    assert crud_tag.count_tags(db) == 1


def test_resolve_or_create_tag_normalizes_unicode_nfc(db: Session):
    composed_name = unicodedata.normalize("NFC", "Café")
    decomposed_name = unicodedata.normalize("NFD", composed_name)
    existing = crud_tag.create_tag(db, TagCreate(name=composed_name, slug="cafe"))

    assert decomposed_name != composed_name
    assert crud_tag.resolve_or_create_tag(db, decomposed_name).id == existing.id
    assert crud_tag.count_tags(db) == 1


def test_resolve_or_create_tag_reuses_existing_when_generated_slug_conflicts(db: Session):
    # “測試”与“测试”名称不同，但都会生成同一个 slug，必须复用已有标签。
    existing = crud_tag.create_tag(db, TagCreate(name="測試", slug="ce-shi"))

    resolved = crud_tag.resolve_or_create_tag(db, "测试")

    assert resolved.id == existing.id
    assert crud_tag.count_tags(db) == 1


def test_resolve_or_create_tags_dedupes_by_resolved_tag_id(db: Session):
    existing = crud_tag.create_tag(db, TagCreate(name="网站", slug="web"))

    resolved = crud_tag.resolve_or_create_tags(db, ["网站", "web", "WEB", " 网站 ", "网站"])

    assert [tag.id for tag in resolved] == [existing.id]


def test_resolve_or_create_tags_respects_limit(db: Session):
    resolved = crud_tag.resolve_or_create_tags(db, ["标签一", "标签二", "标签三"], limit=2)

    assert [tag.name for tag in resolved] == ["标签一", "标签二"]
    assert crud_tag.count_tags(db) == 2


def test_find_conflicting_tag_matches_name_or_slug_across_fields(db: Session):
    existing = crud_tag.create_tag(db, TagCreate(name="网站", slug="web"))

    assert crud_tag.find_conflicting_tag(db, name="web").id == existing.id
    assert crud_tag.find_conflicting_tag(db, slug="网站").id == existing.id
    assert crud_tag.find_conflicting_tag(
        db,
        name="网站",
        slug="web",
        exclude_tag_id=existing.id,
    ) is None
    assert crud_tag.find_conflicting_tag(db, name="全新名称", slug="brand-new") is None
