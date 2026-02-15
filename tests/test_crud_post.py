import pytest
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.category import Category
from rewrz.models.tag import Tag
from rewrz.schemas.user import UserCreate
from rewrz.schemas.post import PostCreate, PostUpdate
from rewrz.schemas.category import CategoryCreate
from rewrz.schemas.tag import TagCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.crud import category as crud_category
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

@pytest.fixture
def test_user(db: Session):
    user_data = UserCreate(username="author", email="author@example.com", password="password")
    return crud_user.create_user(db, user_data)

@pytest.fixture
def test_category(db: Session):
    category_data = CategoryCreate(name="Test Category", slug="test-category")
    return crud_category.create_category(db, category_data)

@pytest.fixture
def test_tag(db: Session):
    tag_data = TagCreate(name="Test Tag", slug="test-tag")
    return crud_tag.create_tag(db, tag_data)

def test_create_post(db: Session, test_user: User, test_category: Category, test_tag: Tag):
    post_data = PostCreate(
        title="Test Post",
        slug="test-post",
        content_markdown="## Hello World\nThis is a test post.",
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        category_ids=[test_category.id],
        tag_ids=[test_tag.id]
    )
    post = crud_post.create_post(db, post_data, author_id=test_user.id)
    assert post.title == "Test Post"
    assert post.slug == "test-post"
    assert post.content_markdown == "## Hello World\nThis is a test post."
    assert post.content_html == ""
    assert post.excerpt == "Hello World This is a test post."
    assert post.post_type == "article"
    assert post.status == "draft"
    assert post.visibility == "public"
    assert post.author_id == test_user.id
    assert len(post.categories) == 1
    assert post.categories[0].name == "Test Category"
    assert len(post.tags) == 1
    assert post.tags[0].name == "Test Tag"
    assert post.created_at is not None
    assert post.updated_at is not None

def test_get_post(db: Session, test_user: User):
    post_data = PostCreate(
        title="Another Post",
        slug="another-post",
        content_markdown="Content",
        post_type="article",
        status="published",
        visibility="public",
        author_id=test_user.id
    )
    created_post = crud_post.create_post(db, post_data, author_id=test_user.id)
    
    fetched_post = crud_post.get_post(db, post_id=created_post.id)
    assert fetched_post.id == created_post.id
    assert fetched_post.title == "Another Post"

def test_get_post_by_slug(db: Session, test_user: User):
    post_data = PostCreate(
        title="Slug Post",
        slug="slug-post",
        content_markdown="Content",
        post_type="article",
        status="published",
        visibility="public",
        author_id=test_user.id
    )
    crud_post.create_post(db, post_data, author_id=test_user.id)
    
    fetched_post = crud_post.get_post_by_slug(db, slug="slug-post")
    assert fetched_post.slug == "slug-post"

def test_get_posts(db: Session, test_user: User):
    crud_post.create_post(db, PostCreate(title="Post 1", slug="post-1", content_markdown="C1", post_type="article", status="published", visibility="public", author_id=test_user.id), author_id=test_user.id)
    crud_post.create_post(db, PostCreate(title="Post 2", slug="post-2", content_markdown="C2", post_type="article", status="draft", visibility="public", author_id=test_user.id), author_id=test_user.id)
    crud_post.create_post(db, PostCreate(title="Post 3", slug="post-3", content_markdown="C3", post_type="page", status="published", visibility="public", author_id=test_user.id), author_id=test_user.id)

    published_posts = crud_post.get_posts(db, status="published")
    assert len(published_posts) == 2 # Post 1 and Post 3

    all_posts = crud_post.get_posts(db)
    assert len(all_posts) == 3

    articles = crud_post.get_posts(db, post_type="article")
    assert len(articles) == 2 # Post 1 and Post 2

def test_update_post(db: Session, test_user: User, test_category: Category):
    post_data = PostCreate(
        title="Original Title",
        slug="original-slug",
        content_markdown="Original Content",
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id
    )
    created_post = crud_post.create_post(db, post_data, author_id=test_user.id)
    
    # Manually update the updated_at field to ensure it's different
    old_updated_at = datetime.now() - timedelta(days=1)
    db.query(Post).filter(Post.id == created_post.id).update({"updated_at": old_updated_at})
    db.commit()
    db.refresh(created_post)
    
    # Save the old updated_at for comparison
    old_time = created_post.updated_at

    update_data = PostUpdate(
        title="Updated Title",
        slug="updated-slug",
        content_markdown="Updated Content",
        status="published",
        category_ids=[test_category.id]
    )
    updated_post = crud_post.update_post(db, post_id=created_post.id, post=update_data)
    assert updated_post.title == "Updated Title"
    assert updated_post.slug == "updated-slug"
    assert updated_post.content_markdown == "Updated Content"
    assert updated_post.content_html == ""
    assert updated_post.status == "published"
    assert updated_post.published_at is not None # Should be set on first publish
    assert updated_post.updated_at > old_time  # Compare with saved old time
    assert len(updated_post.categories) == 1
    assert updated_post.categories[0].name == "Test Category"

def test_delete_post(db: Session, test_user: User):
    post_data = PostCreate(
        title="Delete Me",
        slug="delete-me",
        content_markdown="Content",
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id
    )
    created_post = crud_post.create_post(db, post_data, author_id=test_user.id)

    deleted_post = crud_post.delete_post(db, post_id=created_post.id)
    assert deleted_post.id == created_post.id
    assert crud_post.get_post(db, post_id=created_post.id) is None

def test_post_excerpt_generation(db: Session, test_user: User):
    long_content = "A" * 200
    post_data = PostCreate(
        title="Long Content Post",
        slug="long-content-post",
        content_markdown=long_content,
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        excerpt="" # Empty excerpt
    )
    post = crud_post.create_post(db, post_data, author_id=test_user.id)
    assert post.excerpt == long_content[:120]

    # Test with manual excerpt
    manual_excerpt = "This is a manual excerpt."
    post_data_manual = PostCreate(
        title="Manual Excerpt Post",
        slug="manual-excerpt-post",
        content_markdown=long_content,
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        excerpt=manual_excerpt
    )
    post_manual = crud_post.create_post(db, post_data_manual, author_id=test_user.id)
    assert post_manual.excerpt == manual_excerpt

def test_post_password_visibility(db: Session, test_user: User):
    post_data = PostCreate(
        title="Password Protected",
        slug="password-protected",
        content_markdown="Secret Content",
        post_type="article",
        status="published",
        visibility="password",
        password="secretpassword",
        author_id=test_user.id
    )
    post = crud_post.create_post(db, post_data, author_id=test_user.id)
    assert post.visibility == "password"
    assert post.password is not None # Should be hashed
    
    # Save the old password for comparison
    old_password = post.password

    # Test updating password
    update_data = PostUpdate(password="newsecret")
    updated_post = crud_post.update_post(db, post_id=post.id, post=update_data)
    assert updated_post.password != old_password # Should be re-hashed


def test_create_post_html_mode_stores_only_html(db: Session, test_user: User):
    post_data = PostCreate(
        title="HTML Post",
        slug="html-post",
        content_markdown="",
        content_html="<p><strong>HTML</strong> content</p>",
        editor_mode="html",
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id,
    )
    post = crud_post.create_post(db, post_data, author_id=test_user.id)
    assert post.content_markdown == ""
    assert post.content_html == "<p><strong>HTML</strong> content</p>"


def test_update_post_html_mode_clears_markdown(db: Session, test_user: User):
    post_data = PostCreate(
        title="Switch Me",
        slug="switch-me",
        content_markdown="Markdown content",
        post_type="article",
        status="draft",
        visibility="public",
        author_id=test_user.id,
    )
    created_post = crud_post.create_post(db, post_data, author_id=test_user.id)

    updated = crud_post.update_post(
        db,
        post_id=created_post.id,
        post=PostUpdate(
            editor_mode="html",
            content_markdown="",
            content_html="<h2>HTML body</h2>",
        ),
    )

    assert updated.content_markdown == ""
    assert updated.content_html == "<h2>HTML body</h2>"
