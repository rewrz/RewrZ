import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.post import Post
from rewrz.schemas.category import CategoryCreate, CategoryUpdate
from rewrz.crud import category as crud_category

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

def test_create_category(db: Session):
    category_data = CategoryCreate(name="Test Category", slug="test-category")
    category = crud_category.create_category(db, category_data)
    assert category.name == "Test Category"
    assert category.slug == "test-category"
    assert category.parent_id is None

def test_create_nested_category(db: Session):
    parent_category_data = CategoryCreate(name="Parent Category", slug="parent-category")
    parent_category = crud_category.create_category(db, parent_category_data)

    child_category_data = CategoryCreate(name="Child Category", slug="child-category", parent_id=parent_category.id)
    child_category = crud_category.create_category(db, child_category_data)
    assert child_category.name == "Child Category"
    assert child_category.slug == "child-category"
    assert child_category.parent_id == parent_category.id

def test_get_category(db: Session):
    category_data = CategoryCreate(name="Fetch Category", slug="fetch-category")
    created_category = crud_category.create_category(db, category_data)
    
    fetched_category = crud_category.get_category(db, category_id=created_category.id)
    assert fetched_category.id == created_category.id
    assert fetched_category.name == "Fetch Category"

def test_get_category_by_slug(db: Session):
    category_data = CategoryCreate(name="Slug Category", slug="slug-category")
    crud_category.create_category(db, category_data)
    
    fetched_category = crud_category.get_category_by_slug(db, slug="slug-category")
    assert fetched_category.slug == "slug-category"

def test_get_categories(db: Session):
    crud_category.create_category(db, CategoryCreate(name="Cat1", slug="cat1"))
    crud_category.create_category(db, CategoryCreate(name="Cat2", slug="cat2"))
    
    categories = crud_category.get_categories(db)
    assert len(categories) == 2

def test_update_category(db: Session):
    category_data = CategoryCreate(name="Original Category", slug="original-category")
    created_category = crud_category.create_category(db, category_data)

    update_data = CategoryUpdate(name="Updated Category", slug="updated-category")
    updated_category = crud_category.update_category(db, category_id=created_category.id, category_update=update_data)
    assert updated_category.name == "Updated Category"
    assert updated_category.slug == "updated-category"

    # Test updating parent_id
    new_parent_data = CategoryCreate(name="New Parent", slug="new-parent")
    new_parent = crud_category.create_category(db, new_parent_data)
    update_parent_data = CategoryUpdate(parent_id=new_parent.id)
    updated_category_parent = crud_category.update_category(db, category_id=created_category.id, category_update=update_parent_data)
    assert updated_category_parent.parent_id == new_parent.id

def test_delete_category(db: Session):
    category_data = CategoryCreate(name="Delete Me", slug="delete-me")
    created_category = crud_category.create_category(db, category_data)

    deleted_category = crud_category.delete_category(db, category_id=created_category.id)
    assert deleted_category.id == created_category.id
    assert crud_category.get_category(db, category_id=created_category.id) is None


def test_bulk_delete_categories(db: Session):
    delete_me = crud_category.create_category(db, CategoryCreate(name="Bulk Delete", slug="bulk-delete"))
    used_by_post = crud_category.create_category(db, CategoryCreate(name="Used By Post", slug="used-by-post"))
    delete_me_id = delete_me.id
    used_by_post_id = used_by_post.id

    post = Post(title="Test Post", slug="test-post", content_markdown="x", content_html="<p>x</p>")
    post.categories.append(used_by_post)
    db.add(post)
    db.commit()

    result = crud_category.bulk_delete_categories(db, [delete_me_id, used_by_post_id, 99999])

    assert result["deleted_ids"] == [delete_me_id]
    assert result["blocked_by_posts_ids"] == [used_by_post_id]
    assert result["missing_ids"] == [99999]
    assert crud_category.get_category(db, category_id=delete_me_id) is None
    assert crud_category.get_category(db, category_id=used_by_post_id) is not None


def test_bulk_delete_categories_blocked_by_child(db: Session):
    parent = crud_category.create_category(db, CategoryCreate(name="Parent Bulk", slug="parent-bulk"))
    crud_category.create_category(
        db,
        CategoryCreate(name="Child Bulk", slug="child-bulk", parent_id=parent.id),
    )

    result = crud_category.bulk_delete_categories(db, [parent.id])

    assert result["deleted_ids"] == []
    assert result["blocked_by_children_ids"] == [parent.id]
    assert crud_category.get_category(db, category_id=parent.id) is not None
