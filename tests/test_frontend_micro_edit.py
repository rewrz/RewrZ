"""前台微博发布器：内容分级与前台编辑能力的回归测试。

覆盖四件事：
1. 前台快捷发布接口能把 content_rating 写入数据库。
2. 前台快捷编辑接口只允许作者本人或管理员调用，且编辑后链接（slug）保持不变。
3. `/formats/micro?edit=<id>` 仅在作者/管理员访问时回填发布器，越权一律 404。
4. 编辑时标签按正文重新同步，旧标签不会残留。
"""

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core.database import Base, get_db
from rewrz.core.security import create_access_token, verify_password
from rewrz.crud import post as crud_post
from rewrz.models import Format, Post, User as DbUser
from rewrz.schemas.post import PostCreate


def _seed_users_and_formats(session_local) -> None:
    """预置两个账号与三种内容意图格式，供前台登录态测试使用。"""
    with session_local() as db:
        db.add_all(
            [
                DbUser(
                    id=1,
                    username="micro-admin",
                    hashed_password="hashed",
                    email="micro-admin@example.com",
                    is_active=True,
                    role="super_admin",
                    use_gravatar="auto",
                ),
                DbUser(
                    id=2,
                    username="micro-author",
                    hashed_password="hashed",
                    email="micro-author@example.com",
                    is_active=True,
                    role="user",
                    use_gravatar="auto",
                ),
                DbUser(
                    id=3,
                    username="micro-visitor",
                    hashed_password="hashed",
                    email="micro-visitor@example.com",
                    is_active=True,
                    role="user",
                    use_gravatar="auto",
                ),
            ]
        )
        db.add_all(
            [
                Format(name="标准文章", slug="article"),
                Format(name="微博", slug="micro"),
                Format(name="诗词歌赋", slug="poem"),
            ]
        )
        db.commit()


@pytest.fixture(name="site_client")
def site_client_fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    engine = create_engine(
        f"sqlite:///{tmp_path / f'micro-edit-{uuid4().hex}.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _seed_users_and_formats(session_local)

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


def _login_as(client: TestClient, user_id: int) -> str:
    """以指定用户登录并返回页面里的 CSRF 令牌。"""
    client.cookies.set("access_token", create_access_token({"sub": str(user_id)}))
    response = client.get("/formats/micro")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    assert match is not None, "微博发布器中未找到 CSRF 令牌"
    return match.group(1)


def _create_quick_micro(client: TestClient, csrf_token: str, content: str, **extra) -> dict:
    response = client.post(
        "/api/v1/posts/quick",
        data={
            "content": content,
            "media_items": "[]",
            "csrf_token": csrf_token,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _post_by_slug(session_local, slug: str) -> Post:
    with session_local() as db:
        db_post = db.query(Post).filter(Post.slug == slug).first()
        assert db_post is not None
        db.expunge(db_post)
        return db_post


def _error_message(response) -> str:
    """统一错误响应契约：错误信息位于 error.message。"""
    return str(response.json()["error"]["message"])


def test_quick_create_persists_content_rating(site_client):
    """前台快捷发布要按表单写入内容分级。"""
    client, session_local = site_client
    csrf_token = _login_as(client, 2)

    payload = _create_quick_micro(client, csrf_token, "分级动态 #前台", content_rating="nsfw")

    slug = payload["post_url"].rsplit("/", 1)[-1]
    created = _post_by_slug(session_local, slug)
    assert created.content_rating == "nsfw"
    assert created.author_id == 2


def test_quick_edit_keeps_slug_and_updates_fields(site_client):
    """编辑后链接保持不变，正文、分级、可见性与标签都要同步。"""
    client, session_local = site_client
    csrf_token = _login_as(client, 2)

    created_payload = _create_quick_micro(client, csrf_token, "原始动态 #旧标签")
    post_id = created_payload["id"]
    original_url = created_payload["post_url"]

    response = client.post(
        f"/api/v1/posts/quick/{post_id}",
        data={
            "content": "改过的动态 #新标签",
            "media_items": "[]",
            "visibility": "private",
            "content_rating": "sensitive",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    # 编辑不重建 slug，避免已分享出去的链接失效
    assert payload["post_url"] == original_url

    with session_local() as db:
        db_post = crud_post.get_post(db, post_id=post_id)
        assert db_post is not None
        assert db_post.slug == original_url.rsplit("/", 1)[-1]
        assert "改过的动态" in (db_post.content_markdown or "")
        assert db_post.visibility == "private"
        assert db_post.content_rating == "sensitive"
        assert [tag.name for tag in db_post.tags] == ["新标签"]


def test_quick_edit_rejects_non_author(site_client):
    """非作者且非管理员的账号不能调用前台编辑接口。"""
    client, _session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(client, csrf_token, "别人的动态")

    visitor_csrf = _login_as(client, 3)
    response = client.post(
        f"/api/v1/posts/quick/{created_payload['id']}",
        data={"content": "越权修改", "csrf_token": visitor_csrf},
    )

    assert response.status_code == 403
    assert _error_message(response) == "只能编辑自己发布的动态"


def test_quick_edit_allows_admin(site_client):
    """管理员可以代为编辑任意作者的前台动态。"""
    client, session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(client, csrf_token, "待管理员处理 #原标签")

    admin_csrf = _login_as(client, 1)
    response = client.post(
        f"/api/v1/posts/quick/{created_payload['id']}",
        data={"content": "管理员已修改 #新话题", "csrf_token": admin_csrf},
    )

    assert response.status_code == 200, response.text
    with session_local() as db:
        db_post = crud_post.get_post(db, post_id=created_payload["id"])
        assert "管理员已修改" in (db_post.content_markdown or "")
        assert [tag.name for tag in db_post.tags] == ["新话题"]


def test_quick_edit_rejects_non_micro_post(site_client):
    """只有微博动态可以走前台编辑，普通文章必须回后台。"""
    client, session_local = site_client
    with session_local() as db:
        article_format = db.query(Format).filter(Format.slug == "article").first()
        article = crud_post.create_post(
            db,
            PostCreate(
                title="普通文章",
                slug="plain-article",
                content_markdown="文章正文",
                status="published",
            ),
            author_id=2,
            format_ids=[article_format.id],
        )
        article_id = article.id

    csrf_token = _login_as(client, 2)
    response = client.post(
        f"/api/v1/posts/quick/{article_id}",
        data={"content": "误用微博编辑接口", "csrf_token": csrf_token},
    )

    assert response.status_code == 400
    assert _error_message(response) == "仅支持编辑微博动态"


def test_micro_format_page_prefills_composer_for_author(site_client):
    """作者带上 edit 参数时，发布器切到编辑模式并回填正文与标签。"""
    client, _session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(client, csrf_token, "待编辑正文 #保留标签")

    response = client.get(f"/formats/micro?edit={created_payload['id']}")

    assert response.status_code == 200
    assert f'data-edit-post-id="{created_payload["id"]}"' in response.text
    assert "待编辑正文" in response.text
    assert "#保留标签" in response.text
    assert "保存修改" in response.text
    assert "取消编辑" in response.text


def test_micro_format_page_rejects_other_users_edit_param(site_client):
    """越权或未登录访问 edit 参数一律 404，不泄露动态存在性。"""
    client, _session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(client, csrf_token, "仅作者可编辑")

    _login_as(client, 3)
    assert client.get(f"/formats/micro?edit={created_payload['id']}").status_code == 404

    client.cookies.clear()
    assert client.get(f"/formats/micro?edit={created_payload['id']}").status_code == 404


def test_quick_edit_password_visibility_keeps_old_password(site_client):
    """编辑密码保护动态时留空密码视为沿用旧密码。"""
    client, session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(
        client,
        csrf_token,
        "密码保护动态",
        visibility="password",
        password="旧密码",
    )

    response = client.post(
        f"/api/v1/posts/quick/{created_payload['id']}",
        data={
            "content": "密码保护动态改稿",
            "visibility": "password",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200, response.text
    with session_local() as db:
        db_post = crud_post.get_post(db, post_id=created_payload["id"])
        assert db_post.password
        assert verify_password("旧密码", db_post.password)


def test_micro_detail_page_shows_edit_entry_for_author(site_client):
    """详情页只对作者展示编辑入口，其他访客看不到。"""
    client, _session_local = site_client
    csrf_token = _login_as(client, 2)
    created_payload = _create_quick_micro(client, csrf_token, "详情页编辑入口")
    edit_href = f"/formats/micro?edit={created_payload['id']}"

    author_page = client.get(created_payload["post_url"])
    assert author_page.status_code == 200
    assert edit_href in author_page.text

    _login_as(client, 3)
    other_page = client.get(created_payload["post_url"])
    assert other_page.status_code == 200
    assert edit_href not in other_page.text
