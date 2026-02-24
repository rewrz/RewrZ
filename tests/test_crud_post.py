import pytest
import time
import warnings
from pydantic import ValidationError
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.category import Category
from rewrz.models.tag import Tag
from rewrz.schemas.user import UserCreate
from rewrz.schemas.post import PostCreate, PostUpdate
from rewrz.schemas.comment import CommentCreate
from rewrz.schemas.category import CategoryCreate
from rewrz.schemas.tag import TagCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.crud import comment as crud_comment
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
        post_type="post",
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
    assert post.excerpt == ""
    assert post.post_type == "post"
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
        post_type="post",
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
        post_type="post",
        status="published",
        visibility="public",
        author_id=test_user.id
    )
    crud_post.create_post(db, post_data, author_id=test_user.id)
    
    fetched_post = crud_post.get_post_by_slug(db, slug="slug-post")
    assert fetched_post.slug == "slug-post"

def test_get_posts(db: Session, test_user: User):
    crud_post.create_post(db, PostCreate(title="Post 1", slug="post-1", content_markdown="C1", post_type="post", status="published", visibility="public", author_id=test_user.id), author_id=test_user.id)
    crud_post.create_post(db, PostCreate(title="Post 2", slug="post-2", content_markdown="C2", post_type="post", status="draft", visibility="public", author_id=test_user.id), author_id=test_user.id)
    crud_post.create_post(db, PostCreate(title="Post 3", slug="post-3", content_markdown="C3", post_type="page", status="published", visibility="public", author_id=test_user.id), author_id=test_user.id)

    published_posts = crud_post.get_posts(db, status="published")
    assert len(published_posts) == 2 # Post 1 and Post 3

    all_posts = crud_post.get_posts(db)
    assert len(all_posts) == 3

    articles = crud_post.get_posts(db, post_type="post")
    assert len(articles) == 2 # Post 1 and Post 2

    with pytest.raises(ValueError):
        crud_post.get_posts(db, post_type="article")


def test_get_public_post_conditions_helper(db: Session, test_user: User):
    crud_post.create_post(
        db,
        PostCreate(
            title="Published Post",
            slug="published-post",
            content_markdown="C1",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    crud_post.create_post(
        db,
        PostCreate(
            title="Draft Post",
            slug="draft-post",
            content_markdown="C2",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    crud_post.create_post(
        db,
        PostCreate(
            title="Published Page",
            slug="published-page",
            content_markdown="C3",
            post_type="page",
            status="published",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )

    public_count = db.execute(
        select(func.count(Post.id)).where(*crud_post.get_public_post_conditions())
    ).scalar_one()
    type_only_count = db.execute(
        select(func.count(Post.id)).where(*crud_post.get_public_post_conditions(published_only=False))
    ).scalar_one()

    assert public_count == 1
    assert type_only_count == 2

def test_update_post(db: Session, test_user: User, test_category: Category):
    post_data = PostCreate(
        title="Original Title",
        slug="original-slug",
        content_markdown="Original Content",
        post_type="post",
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
        post_type="post",
        status="draft",
        visibility="public",
        author_id=test_user.id
    )
    created_post = crud_post.create_post(db, post_data, author_id=test_user.id)

    deleted_post = crud_post.delete_post(db, post_id=created_post.id)
    assert deleted_post.id == created_post.id
    assert crud_post.get_post(db, post_id=created_post.id) is None


def test_delete_post_also_deletes_related_comments(db: Session, test_user: User):
    created_post = crud_post.create_post(
        db,
        PostCreate(
            title="Delete With Comments",
            slug="delete-with-comments",
            content_markdown="Content",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )

    parent = crud_comment.create_comment(
        db,
        CommentCreate(
            post_id=created_post.id,
            author_name="A",
            author_email="a@example.com",
            content="Parent",
            status="approved",
        ),
    )
    crud_comment.create_comment(
        db,
        CommentCreate(
            post_id=created_post.id,
            parent_id=parent.id,
            author_name="B",
            author_email="b@example.com",
            content="Child",
            status="approved",
        ),
    )

    deleted_post = crud_post.delete_post(db, post_id=created_post.id)
    assert deleted_post is not None
    assert crud_post.get_post(db, post_id=created_post.id) is None
    assert crud_comment.get_comments_for_post(db, created_post.id) == []


def test_delete_posts_by_ids_only_deletes_target_author_posts(db: Session, test_user: User):
    another_user = crud_user.create_user(
        db,
        UserCreate(username="another", email="another@example.com", password="password"),
    )

    owned_post_1 = crud_post.create_post(
        db,
        PostCreate(
            title="Owned Post 1",
            slug="owned-post-1",
            content_markdown="Content",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    owned_post_2 = crud_post.create_post(
        db,
        PostCreate(
            title="Owned Post 2",
            slug="owned-post-2",
            content_markdown="Content",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    other_user_post = crud_post.create_post(
        db,
        PostCreate(
            title="Other User Post",
            slug="other-user-post",
            content_markdown="Content",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=another_user.id,
        ),
        author_id=another_user.id,
    )

    deleted_count = crud_post.delete_posts_by_ids(
        db,
        post_ids=[owned_post_1.id, owned_post_2.id, other_user_post.id, owned_post_2.id],
        author_id=test_user.id,
    )

    assert deleted_count == 2
    assert crud_post.get_post(db, post_id=owned_post_1.id) is None
    assert crud_post.get_post(db, post_id=owned_post_2.id) is None
    assert crud_post.get_post(db, post_id=other_user_post.id) is not None


def test_delete_posts_by_ids_also_deletes_comments_for_deleted_posts(db: Session, test_user: User):
    another_user = crud_user.create_user(
        db,
        UserCreate(username="another2", email="another2@example.com", password="password"),
    )

    owned_post = crud_post.create_post(
        db,
        PostCreate(
            title="Owned Post With Comment",
            slug="owned-post-with-comment",
            content_markdown="Content",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    other_user_post = crud_post.create_post(
        db,
        PostCreate(
            title="Other Post With Comment",
            slug="other-post-with-comment",
            content_markdown="Content",
            post_type="post",
            status="published",
            visibility="public",
            author_id=another_user.id,
        ),
        author_id=another_user.id,
    )

    crud_comment.create_comment(
        db,
        CommentCreate(
            post_id=owned_post.id,
            author_name="Owned",
            author_email="owned@example.com",
            content="Owned comment",
            status="approved",
        ),
    )
    crud_comment.create_comment(
        db,
        CommentCreate(
            post_id=other_user_post.id,
            author_name="Other",
            author_email="other@example.com",
            content="Other comment",
            status="approved",
        ),
    )

    deleted_count = crud_post.delete_posts_by_ids(
        db,
        post_ids=[owned_post.id, other_user_post.id],
        author_id=test_user.id,
    )

    assert deleted_count == 1
    assert crud_post.get_post(db, post_id=owned_post.id) is None
    assert crud_post.get_post(db, post_id=other_user_post.id) is not None
    assert crud_comment.get_comments_for_post(db, owned_post.id) == []
    assert len(crud_comment.get_comments_for_post(db, other_user_post.id)) == 1


def test_bulk_update_posts_status_by_ids_only_updates_target_author_posts(db: Session, test_user: User):
    another_user = crud_user.create_user(
        db,
        UserCreate(username="bulkstatus", email="bulkstatus@example.com", password="password"),
    )

    owned_draft = crud_post.create_post(
        db,
        PostCreate(
            title="Owned Draft",
            slug="owned-draft",
            content_markdown="Content",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    owned_published = crud_post.create_post(
        db,
        PostCreate(
            title="Owned Published",
            slug="owned-published",
            content_markdown="Content",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
        ),
        author_id=test_user.id,
    )
    other_user_post = crud_post.create_post(
        db,
        PostCreate(
            title="Other User Draft",
            slug="other-user-draft",
            content_markdown="Content",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=another_user.id,
        ),
        author_id=another_user.id,
    )

    updated_count = crud_post.bulk_update_posts_status_by_ids(
        db,
        post_ids=[owned_draft.id, owned_published.id, other_user_post.id, owned_draft.id],
        status="published",
        author_id=test_user.id,
    )

    assert updated_count == 2
    assert crud_post.get_post(db, post_id=owned_draft.id).status == "published"
    assert crud_post.get_post(db, post_id=owned_draft.id).published_at is not None
    assert crud_post.get_post(db, post_id=other_user_post.id).status == "draft"

    drafted_count = crud_post.bulk_update_posts_status_by_ids(
        db,
        post_ids=[owned_draft.id, owned_published.id],
        status="draft",
        author_id=test_user.id,
    )
    assert drafted_count == 2
    assert crud_post.get_post(db, post_id=owned_draft.id).status == "draft"
    assert crud_post.get_post(db, post_id=owned_draft.id).published_at is None
    assert crud_post.get_post(db, post_id=owned_published.id).status == "draft"
    assert crud_post.get_post(db, post_id=owned_published.id).published_at is None

def test_post_excerpt_generation(db: Session, test_user: User):
    long_content = "A" * 200
    post_data = PostCreate(
        title="Long Content Post",
        slug="long-content-post",
        content_markdown=long_content,
        post_type="post",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        excerpt="" # Empty excerpt
    )
    post = crud_post.create_post(db, post_data, author_id=test_user.id)
    assert post.excerpt == ""

    # Test with manual excerpt
    manual_excerpt = "This is a manual excerpt."
    post_data_manual = PostCreate(
        title="Manual Excerpt Post",
        slug="manual-excerpt-post",
        content_markdown=long_content,
        post_type="post",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        excerpt=manual_excerpt
    )
    post_manual = crud_post.create_post(db, post_data_manual, author_id=test_user.id)
    assert post_manual.excerpt == manual_excerpt

    updated_post = crud_post.update_post(
        db,
        post_id=post_manual.id,
        post=PostUpdate(excerpt=""),
    )
    assert updated_post.excerpt == ""

def test_post_password_visibility(db: Session, test_user: User):
    post_data = PostCreate(
        title="Password Protected",
        slug="password-protected",
        content_markdown="Secret Content",
        post_type="post",
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
        post_type="post",
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
        post_type="post",
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


def test_post_schema_rejects_legacy_article_post_type():
    with pytest.raises(ValidationError):
        PostCreate(
            title="Invalid Type",
            slug="invalid-type",
            content_markdown="x",
            post_type="article",
            status="draft",
            visibility="public",
        )


def test_normalize_legacy_article_post_type(db: Session, test_user: User):
    post = Post(
        title="Legacy Type",
        slug="legacy-type",
        content_markdown="legacy",
        content_html="",
        post_type="article",
        status="published",
        visibility="public",
        author_id=test_user.id,
    )
    db.add(post)
    db.commit()

    updated_count = crud_post.normalize_legacy_article_post_type(db)
    assert updated_count == 1

    refreshed = crud_post.get_post_by_slug(db, "legacy-type")
    assert refreshed is not None
    assert refreshed.post_type == "post"


def test_create_post_auto_create_default_format_without_sawarning(db: Session, test_user: User):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        created_post = crud_post.create_post(
            db,
            PostCreate(
                title="自动格式测试",
                slug="auto-format-check",
                content_markdown="内容",
                post_type="post",
                status="draft",
                visibility="public",
                author_id=test_user.id,
            ),
            author_id=test_user.id,
        )

    sa_warnings = [item for item in caught if issubclass(item.category, SAWarning)]
    assert sa_warnings == []
    assert any(fmt.slug == "article" for fmt in created_post.formats)

