import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.comment import Comment
from rewrz.schemas.user import UserCreate
from rewrz.schemas.post import PostCreate
from rewrz.schemas.comment import CommentCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.crud import comment as crud_comment

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
def test_post(db: Session, test_user: User):
    post_data = PostCreate(
        title="Test Post for Comments",
        slug="test-post-comments",
        content_markdown="Content",
        post_type="article",
        status="published",
        visibility="public"
    )
    return crud_post.create_post(db, post_data, author_id=test_user.id)

def test_create_comment(db: Session, test_post: Post):
    comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Commenter 1",
        author_email="commenter1@example.com",
        content="This is a test comment."
    )
    comment = crud_comment.create_comment(db, comment_data)
    assert comment.post_id == test_post.id
    assert comment.author_name == "Commenter 1"
    assert comment.content == "This is a test comment."
    assert comment.status == "pending" # Default status


def test_create_comment_persists_ip_and_user_agent(db: Session, test_post: Post):
    comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Commenter With Meta",
        author_email="commenter-meta@example.com",
        content="Testing metadata persistence.",
        ip_address="203.0.113.77",
        user_agent="pytest-agent/1.0",
    )
    comment = crud_comment.create_comment(db, comment_data)

    assert comment.ip_address == "203.0.113.77"
    assert comment.user_agent == "pytest-agent/1.0"

def test_create_nested_comment(db: Session, test_post: Post):
    parent_comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Parent Commenter",
        author_email="parent@example.com",
        content="This is a parent comment."
    )
    parent_comment = crud_comment.create_comment(db, parent_comment_data)

    child_comment_data = CommentCreate(
        post_id=test_post.id,
        parent_id=parent_comment.id,
        author_name="Child Commenter",
        author_email="child@example.com",
        content="This is a reply."
    )
    child_comment = crud_comment.create_comment(db, child_comment_data)
    assert child_comment.parent_id == parent_comment.id

def test_get_comment(db: Session, test_post: Post):
    comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Fetch Commenter",
        author_email="fetch@example.com",
        content="Fetch content."
    )
    created_comment = crud_comment.create_comment(db, comment_data)
    
    fetched_comment = crud_comment.get_comment(db, comment_id=created_comment.id)
    assert fetched_comment.id == created_comment.id
    assert fetched_comment.author_name == "Fetch Commenter"

def test_get_comments_for_post(db: Session, test_post: Post):
    crud_comment.create_comment(db, CommentCreate(post_id=test_post.id, author_name="C1", author_email="c1@e.com", content="Comment 1"))
    crud_comment.create_comment(db, CommentCreate(post_id=test_post.id, author_name="C2", author_email="c2@e.com", content="Comment 2"))
    
    comments = crud_comment.get_comments_for_post(db, post_id=test_post.id)
    assert len(comments) == 2

def test_update_comment_status(db: Session, test_post: Post):
    comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Status Commenter",
        author_email="status@example.com",
        content="Content for status update."
    )
    created_comment = crud_comment.create_comment(db, comment_data)
    assert created_comment.status == "pending"

    updated_comment = crud_comment.update_comment_status(db, comment_id=created_comment.id, status="approved")
    assert updated_comment.status == "approved"

def test_delete_comment(db: Session, test_post: Post):
    comment_data = CommentCreate(
        post_id=test_post.id,
        author_name="Delete Commenter",
        author_email="delete@example.com",
        content="Content to delete."
    )
    created_comment = crud_comment.create_comment(db, comment_data)

    deleted_comment = crud_comment.delete_comment(db, comment_id=created_comment.id)
    assert deleted_comment.id == created_comment.id
    assert crud_comment.get_comment(db, comment_id=created_comment.id) is None
