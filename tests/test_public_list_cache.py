"""公开列表页缓存（首页、分类、标签）的回归测试。"""

import re
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core import public_list_cache
from rewrz.core.database import Base, get_db
from rewrz.core.security import create_access_token
from rewrz.crud import post as crud_post
from rewrz.models import Category, Post, Tag, User as DbUser
from rewrz.schemas import PostCreate


def _set_installation_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )


@pytest.fixture
def public_client(monkeypatch, tmp_path):
    """构造带独立数据库的公开站点客户端，避免污染其他测试库。"""
    _set_installation_complete(monkeypatch)
    db_path = tmp_path / f"public-list-cache-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with session_local() as db:
        db.add(
            DbUser(
                id=1,
                username="cache-admin",
                hashed_password="hashed",
                email="cache-admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
            )
        )
        db.commit()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(main_module.app), session_local
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _insert_published_post(
    session_local,
    *,
    title: str,
    slug: str | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
) -> int:
    """直接写库，绕过 CRUD 失效逻辑，用于验证缓存确实被命中。"""
    with session_local() as db:
        post = Post(
            title=title,
            slug=slug or f"cache-post-{uuid4().hex[:8]}",
            content_markdown="缓存测试正文",
            content_html="<p>缓存测试正文</p>",
            excerpt="缓存测试正文",
            post_type="post",
            status="published",
            visibility="public",
            author_id=1,
            published_at=datetime(2026, 1, 1, 8, 0, 0),
        )
        if category_id is not None:
            category = db.query(Category).filter(Category.id == category_id).one()
            post.categories.append(category)
        if tag_id is not None:
            tag = db.query(Tag).filter(Tag.id == tag_id).one()
            post.tags.append(tag)
        db.add(post)
        db.commit()
        return int(post.id)


def _extract_theme_csrf_token(html: str) -> str:
    match = re.search(r'data-theme-csrf-token="([^"]*)"', html)
    assert match is not None
    return match.group(1)


def test_homepage_cache_hit_skips_database_reads(public_client):
    client, session_local = public_client

    first = client.get("/")
    assert first.status_code == 200

    _insert_published_post(session_local, title="缓存外的新文章")
    second = client.get("/")
    assert second.status_code == 200
    assert "缓存外的新文章" not in second.text

    public_list_cache.invalidate_public_list_cache()
    third = client.get("/")
    assert "缓存外的新文章" in third.text


def test_create_post_invalidates_list_cache(public_client):
    client, session_local = public_client

    assert client.get("/").status_code == 200

    with session_local() as db:
        crud_post.create_post(
            db,
            PostCreate(title="写入后立即可见", content_markdown="正文", status="published"),
            author_id=1,
        )

    response = client.get("/")
    assert "写入后立即可见" in response.text


def test_authenticated_request_bypasses_cache(public_client):
    client, session_local = public_client
    token = create_access_token({"sub": "1", "username": "cache-admin", "token_version": 1})
    client.cookies.set("access_token", token)

    assert client.get("/").status_code == 200

    _insert_published_post(session_local, title="登录用户可见的新文章")
    response = client.get("/")
    assert "登录用户可见的新文章" in response.text


def test_htmx_request_bypasses_cache(public_client):
    client, session_local = public_client

    assert client.get("/").status_code == 200

    _insert_published_post(session_local, title="HTMX 请求的新文章")
    response = client.get("/", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "HTMX 请求的新文章" in response.text
    # 分页片段绝不能进入共享缓存，否则会被当成整页发给普通访客。
    assert "no-store" in response.headers.get("cache-control", "")


def test_anonymous_list_page_skips_session_and_enables_edge_cache(public_client):
    """匿名列表页不写会话：无 Set-Cookie、无 Vary: Cookie，允许 CDN 整页缓存。"""
    client, _ = public_client

    first = client.get("/")
    assert first.status_code == 200
    assert "set-cookie" not in first.headers
    assert "cookie" not in str(first.headers.get("vary", "")).lower()
    assert "s-maxage=20" in first.headers.get("cache-control", "")
    # 列表页没有需要 CSRF 令牌的表单，令牌保持为空。
    assert _extract_theme_csrf_token(first.text) == ""

    # 新访客命中进程内缓存时行为一致，不会因为共享令牌而泄露会话。
    second = TestClient(main_module.app).get("/")
    assert second.status_code == 200
    assert "set-cookie" not in second.headers
    assert "s-maxage=20" in second.headers.get("cache-control", "")
    assert _extract_theme_csrf_token(second.text) == ""


def test_authenticated_list_page_keeps_csrf_token_without_edge_cache(public_client):
    """已登录用户仍创建会话令牌，且响应不能进入共享缓存。"""
    client, _ = public_client
    token = create_access_token({"sub": "1", "username": "cache-admin", "token_version": 1})
    client.cookies.set("access_token", token)

    response = client.get("/")
    assert response.status_code == 200
    assert _extract_theme_csrf_token(response.text)
    assert "no-store" in response.headers.get("cache-control", "")


def test_guest_theme_cookie_uses_separate_cache_entry(public_client):
    client, _ = public_client
    dark_client = TestClient(main_module.app)
    dark_client.cookies.set("rewrz_theme", "dark")

    dark = dark_client.get("/")
    assert 'data-current-theme="dark"' in dark.text
    # CDN 缓存键只有 URL，带主题 Cookie 的响应必须禁止边缘缓存
    assert "no-store" in dark.headers.get("cache-control", "")

    light = client.get("/")
    assert 'data-current-theme="light"' in light.text

    light_cached = client.get("/")
    assert 'data-current-theme="light"' in light_cached.text

    dark_cached = dark_client.get("/")
    assert 'data-current-theme="dark"' in dark_cached.text


def test_category_archive_cache_and_invalidation(public_client):
    client, session_local = public_client

    with session_local() as db:
        category = Category(name="缓存分类", slug=f"cache-cat-{uuid4().hex[:8]}")
        db.add(category)
        db.commit()
        category_id = int(category.id)
        category_slug = category.slug

    archive_url = f"/archives/by-category/{category_slug}"
    assert client.get(archive_url).status_code == 200

    _insert_published_post(
        session_local,
        title="分类缓存后的新文章",
        category_id=category_id,
    )
    assert "分类缓存后的新文章" not in client.get(archive_url).text

    public_list_cache.invalidate_public_list_cache()
    assert "分类缓存后的新文章" in client.get(archive_url).text

    assert client.get("/archives/by-category/not-exists").status_code == 404


def test_tag_archive_cache_and_invalidation(public_client):
    client, session_local = public_client

    with session_local() as db:
        tag = Tag(name="缓存标签", slug=f"cache-tag-{uuid4().hex[:8]}")
        db.add(tag)
        db.commit()
        tag_id = int(tag.id)
        tag_slug = tag.slug

    archive_url = f"/archives/by-tag/{tag_slug}"
    assert client.get(archive_url).status_code == 200

    _insert_published_post(
        session_local,
        title="标签缓存后的新文章",
        tag_id=tag_id,
    )
    assert "标签缓存后的新文章" not in client.get(archive_url).text

    public_list_cache.invalidate_public_list_cache()
    assert "标签缓存后的新文章" in client.get(archive_url).text
