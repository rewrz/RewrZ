#!/usr/bin/env python3
"""
内容类型系统集成测试

验证文章只使用单一主类型（article / micro / poem）。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.schemas.user import UserCreate
from rewrz.schemas.post import PostCreate
from rewrz.schemas.format import FormatCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.crud import format as crud_format


SQLALCHEMY_DATABASE_URL = "sqlite:///./tests/test_multi_format.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(name="db")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db: Session):
    return crud_user.create_user(
        db,
        UserCreate(username="testuser", email="test@example.com", password="testpass123"),
    )


@pytest.fixture
def test_formats(db: Session):
    formats_data = [
        ("标准文章", "article"),
        ("微博", "micro"),
        ("诗词歌赋", "poem"),
        ("旧视频格式", "video"),
    ]
    formats = []
    for name, slug in formats_data:
        formats.append(crud_format.create_format(db, FormatCreate(name=name, slug=slug)))
    return formats


def test_create_posts_with_single_intent(db: Session, test_user: User, test_formats: list):
    article_fmt = next(f for f in test_formats if f.slug == "article")
    micro_fmt = next(f for f in test_formats if f.slug == "micro")
    poetry_fmt = next(f for f in test_formats if f.slug == "poem")

    article_post = crud_post.create_post(
        db,
        PostCreate(
            title="标准文章",
            content_markdown="content",
            post_type="post",
            status="published",
            visibility="public",
            format_ids=[article_fmt.id],
        ),
        author_id=test_user.id,
    )
    micro_post = crud_post.create_post(
        db,
        PostCreate(
            title="短动态",
            content_markdown="hello micro",
            post_type="post",
            status="published",
            visibility="public",
            format_ids=[micro_fmt.id],
        ),
        author_id=test_user.id,
    )
    poetry_post = crud_post.create_post(
        db,
        PostCreate(
            title="诗词",
            content_markdown="春眠不觉晓",
            post_type="post",
            status="published",
            visibility="public",
            format_ids=[poetry_fmt.id],
        ),
        author_id=test_user.id,
    )

    assert [fmt.slug for fmt in article_post.formats] == ["article"]
    assert [fmt.slug for fmt in micro_post.formats] == ["micro"]
    assert [fmt.slug for fmt in poetry_post.formats] == ["poem"]


def test_non_intent_format_falls_back_to_article(db: Session, test_user: User, test_formats: list):
    legacy_video = next(f for f in test_formats if f.slug == "video")

    post = crud_post.create_post(
        db,
        PostCreate(
            title="旧格式输入",
            content_markdown="legacy",
            post_type="post",
            status="published",
            visibility="public",
            format_ids=[legacy_video.id],
        ),
        author_id=test_user.id,
    )

    assert [fmt.slug for fmt in post.formats] == ["article"]


def test_multiple_format_ids_normalize_to_one_primary_intent(db: Session, test_user: User, test_formats: list):
    article_fmt = next(f for f in test_formats if f.slug == "article")
    micro_fmt = next(f for f in test_formats if f.slug == "micro")
    poetry_fmt = next(f for f in test_formats if f.slug == "poem")

    post = crud_post.create_post(
        db,
        PostCreate(
            title="多意图输入",
            content_markdown="priority",
            post_type="post",
            status="published",
            visibility="public",
            format_ids=[article_fmt.id, poetry_fmt.id, micro_fmt.id],
        ),
        author_id=test_user.id,
    )

    # 当前优先级：micro > poem > article
    assert [fmt.slug for fmt in post.formats] == ["micro"]


def test_get_posts_by_intent(db: Session, test_user: User, test_formats: list):
    article_fmt = next(f for f in test_formats if f.slug == "article")
    micro_fmt = next(f for f in test_formats if f.slug == "micro")

    for title, format_ids in [
        ("动态1", [micro_fmt.id]),
        ("动态2", [micro_fmt.id]),
        ("文章1", [article_fmt.id]),
    ]:
        crud_post.create_post(
            db,
            PostCreate(
                title=title,
                content_markdown=title,
                post_type="post",
                status="published",
                visibility="public",
                format_ids=format_ids,
            ),
            author_id=test_user.id,
        )

    micro_posts = crud_post.get_posts_by_format(db, micro_fmt.id)
    article_posts = crud_post.get_posts_by_format(db, article_fmt.id)

    assert len(micro_posts) == 2
    assert len(article_posts) == 1
    assert all([fmt.slug for fmt in post.formats] == ["micro"] for post in micro_posts)
    assert all([fmt.slug for fmt in post.formats] == ["article"] for post in article_posts)


def test_auto_slug_generation(db: Session, test_user: User, test_formats: list):
    article_fmt = next(f for f in test_formats if f.slug == "article")

    post_without_slug = PostCreate(
        title="测试自动生成Slug的文章",
        content_markdown="这是测试内容",
        post_type="post",
        status="published",
        visibility="public",
        format_ids=[article_fmt.id],
    )
    created_post = crud_post.create_post(db, post_without_slug, author_id=test_user.id)

    assert created_post.slug is not None
    assert created_post.slug == "ce-shi-zi-dong-sheng-cheng-slugde-wen-zhang"

    duplicate_post = PostCreate(
        title="测试自动生成Slug的文章",
        content_markdown="这是另一篇测试内容",
        post_type="post",
        status="published",
        visibility="public",
        format_ids=[article_fmt.id],
    )
    created_duplicate = crud_post.create_post(db, duplicate_post, author_id=test_user.id)

    assert created_duplicate.slug != created_post.slug
    assert created_duplicate.slug == "ce-shi-zi-dong-sheng-cheng-slugde-wen-zhang-1"



