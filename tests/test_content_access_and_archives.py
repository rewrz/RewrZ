import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.tag import Tag
from rewrz.schemas.user import UserCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.core.content_access import (
    extract_hide_block,
    render_markdown_with_hide_blocks,
)
from rewrz.core.toc import build_toc_from_html
from rewrz.core.template_filters import extract_image_urls_filter, post_url_filter


SQLALCHEMY_DATABASE_URL = "sqlite:///./tests/test_content_access.db"
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
    user_data = UserCreate(username="archive_author", email="archive@example.com", password="password")
    return crud_user.create_user(db, user_data)


def test_hide_block_rendering_locked_and_unlocked():
    md = "公开内容\n\n[hide]这是隐藏段落 **secret**[/hide]\n\n结尾"

    locked_html = render_markdown_with_hide_blocks(md, post_id=12, can_view_hidden=False)
    assert "这是隐藏段落" not in locked_html
    assert "hx-post=\"/api/v1/reveal/12?index=0\"" in locked_html

    unlocked_html = render_markdown_with_hide_blocks(md, post_id=12, can_view_hidden=True)
    assert "这是隐藏段落" in unlocked_html
    assert "<strong>secret</strong>" in unlocked_html


def test_extract_hide_block():
    md = "[hide]A[/hide]\n正文\n[hide]B[/hide]"
    assert extract_hide_block(md, 0) == "A"
    assert extract_hide_block(md, 1) == "B"
    assert extract_hide_block(md, 2) is None


def test_get_posts_by_year_month_and_archives(db: Session, test_user: User):
    posts = [
        Post(
            title="Jan Post",
            slug="jan-post",
            content_markdown="a",
            content_html="<p>a</p>",
            excerpt="a",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
            published_at=datetime(2026, 1, 15, 10, 0, 0),
        ),
        Post(
            title="Jan Article",
            slug="jan-article",
            content_markdown="b",
            content_html="<p>b</p>",
            excerpt="b",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
            published_at=datetime(2026, 1, 20, 9, 0, 0),
        ),
        Post(
            title="Feb Post",
            slug="feb-post",
            content_markdown="c",
            content_html="<p>c</p>",
            excerpt="c",
            post_type="post",
            status="published",
            visibility="public",
            author_id=test_user.id,
            published_at=datetime(2026, 2, 1, 8, 0, 0),
        ),
        Post(
            title="Draft Post",
            slug="draft-post",
            content_markdown="d",
            content_html="<p>d</p>",
            excerpt="d",
            post_type="post",
            status="draft",
            visibility="public",
            author_id=test_user.id,
            published_at=datetime(2026, 1, 11, 8, 0, 0),
        ),
        Post(
            title="Page Jan",
            slug="page-jan",
            content_markdown="e",
            content_html="<p>e</p>",
            excerpt="e",
            post_type="page",
            status="published",
            visibility="public",
            author_id=test_user.id,
            published_at=datetime(2026, 1, 5, 8, 0, 0),
        ),
    ]
    db.add_all(posts)
    db.commit()

    jan_posts = crud_post.get_posts_by_year_month(db, year=2026, month=1)
    jan_slugs = [p.slug for p in jan_posts]
    assert jan_slugs == ["jan-article", "jan-post"]

    all_archive_posts = crud_post.get_archive_posts(db)
    archive_slugs = [p.slug for p in all_archive_posts]
    assert archive_slugs == ["feb-post", "jan-article", "jan-post"]


def test_get_posts_by_tag_filters_published_articles(db: Session, test_user: User):
    tag = Tag(name="TagA", slug="tag-a")
    db.add(tag)
    db.flush()

    published_post = Post(
        title="Published Tagged",
        slug="published-tagged",
        content_markdown="x",
        content_html="<p>x</p>",
        excerpt="x",
        post_type="post",
        status="published",
        visibility="public",
        author_id=test_user.id,
        published_at=datetime(2026, 1, 2, 10, 0, 0),
        tags=[tag],
    )
    draft_post = Post(
        title="Draft Tagged",
        slug="draft-tagged",
        content_markdown="y",
        content_html="<p>y</p>",
        excerpt="y",
        post_type="post",
        status="draft",
        visibility="public",
        author_id=test_user.id,
        tags=[tag],
    )
    tagged_page = Post(
        title="Page Tagged",
        slug="page-tagged",
        content_markdown="z",
        content_html="<p>z</p>",
        excerpt="z",
        post_type="page",
        status="published",
        visibility="public",
        author_id=test_user.id,
        published_at=datetime(2026, 1, 3, 10, 0, 0),
        tags=[tag],
    )
    db.add_all([published_post, draft_post, tagged_page])
    db.commit()

    tag_posts = crud_post.get_posts_by_tag(db, tag_id=tag.id)
    assert [p.slug for p in tag_posts] == ["published-tagged"]


def test_build_toc_from_html():
    html = "<h2>一</h2><p>a</p><h3>二</h3><p>b</p><h2>三</h2><p>c</p>"
    processed_html, toc_items = build_toc_from_html(html, min_headings=3)
    assert len(toc_items) == 3
    assert toc_items[0]["level"] == "h2"
    assert toc_items[1]["level"] == "h3"
    assert "id=" in processed_html


def test_post_url_filter_uses_canonical_intent_segment():
    class _Format:
        def __init__(self, slug):
            self.slug = slug

    class _Post:
        def __init__(self, slug, format_slug):
            self.slug = slug
            self.formats = [_Format(format_slug)]

    assert post_url_filter(_Post("p1", "micro")) == "/micro/p1"
    assert post_url_filter(_Post("p2", "article")) == "/article/p2"
    assert post_url_filter(_Post("p3", "poem")) == "/poem/p3"


def test_extract_image_urls_filter_deduplicates_and_skips_featured():
    html = (
        '<p>x</p>'
        '<img src="/media/a.jpg">'
        '<img src="/media/featured.jpg">'
        '<img src="/media/a.jpg">'
        '<img src="/media/b.jpg">'
    )
    urls = extract_image_urls_filter(html, featured_image_url="/media/featured.jpg")
    assert urls == ["/media/a.jpg", "/media/b.jpg"]


