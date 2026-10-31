"""列表页内联编辑接口测试。

覆盖轻量更新路径的关键约束：
- 改标题不改 slug
- 转草稿保留发布时间
- 不写版本快照
- 分类、标签、发布时间按预期更新
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.api import posts as posts_api
from rewrz.core.config import settings as app_settings
from rewrz.core.database import get_db
from rewrz.core.security import get_current_user
from rewrz.core.time_utils import site_local_to_utc_naive
from rewrz.crud import post as crud_post
from rewrz.models.category import Category
from rewrz.models.format import Format
from rewrz.models.post import Post as PostModel
from rewrz.models.user import User as DbUser
from rewrz.schemas.post import PostCreate, PostUpdate


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _ensure_admin_routes_registered() -> None:
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True


def _build_client(test_db, monkeypatch) -> TestClient:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    # 内联接口的 CSRF 校验依赖浏览器会话，测试中直接放行，鉴权仍走依赖覆盖。
    monkeypatch.setattr(posts_api, "verify_csrf_token", lambda request, token: None)
    main_module.app.dependency_overrides[get_db] = lambda: test_db
    main_module.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )
    return TestClient(main_module.app)


def _inline_url(post_id: int) -> str:
    return f"{app_settings.ADMIN_PATH.rstrip('/')}/api/v1/posts/{post_id}/inline"


@pytest.fixture()
def inline_setup(test_db, monkeypatch):
    user = test_db.query(DbUser).filter(DbUser.id == 1).first()
    if user is None:
        user = DbUser(
            id=1,
            username="admin",
            hashed_password="hashed",
            email="admin@example.com",
            is_active=True,
            role="super_admin",
            use_gravatar="auto",
            display_name="管理员",
        )
        test_db.add(user)
        test_db.commit()

    # 测试引擎在会话级共享，分类与文章使用唯一后缀避免跨用例的唯一约束冲突。
    suffix = uuid4().hex[:8]
    category_a = Category(name=f"技术-{suffix}", slug=f"tech-{suffix}")
    category_b = Category(name=f"随笔-{suffix}", slug=f"essay-{suffix}")
    test_db.add_all([category_a, category_b])
    test_db.commit()
    test_db.refresh(category_a)
    test_db.refresh(category_b)

    post = PostModel(
        title="原始标题",
        slug=f"original-slug-{suffix}",
        content_markdown="原始正文",
        content_html="<p>原始正文</p>",
        excerpt="原始摘要",
        post_type="post",
        status="published",
        visibility="public",
        published_at=datetime(2026, 1, 2, 3, 4, 5),
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
        author_id=1,
        version_snapshots=[],
    )
    post.categories.append(category_a)
    test_db.add(post)
    test_db.commit()
    test_db.refresh(post)

    client = _build_client(test_db, monkeypatch)
    try:
        yield SimpleNamespace(
            client=client,
            db=test_db,
            post=post,
            category_a=category_a,
            category_b=category_b,
            monkeypatch=monkeypatch,
            suffix=suffix,
        )
    finally:
        main_module.app.dependency_overrides.clear()


def _patch(client: TestClient, post_id: int, payload: dict):
    return client.patch(
        _inline_url(post_id),
        json=payload,
        headers={"X-CSRF-Token": "test-token"},
    )


def _error_message(response) -> str:
    """项目统一错误处理器把提示放在 error.message 中。"""
    return response.json()["error"]["message"]


def test_inline_title_update_keeps_slug_time_and_snapshot(inline_setup):
    post_id = inline_setup.post.id
    update_calls: list[bool] = []
    inline_setup.monkeypatch.setattr(
        crud_post,
        "_invalidate_public_caches",
        lambda: update_calls.append(True),
    )

    response = _patch(inline_setup.client, post_id, {"title": "新的标题"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["post"]["title"] == "新的标题"
    assert data["post"]["title_display"] == "新的标题"

    db_post = inline_setup.db.get(PostModel, post_id)
    inline_setup.db.refresh(db_post)
    assert db_post.title == "新的标题"
    # 列表页改标题不能改变文章链接
    assert db_post.slug == f"original-slug-{inline_setup.suffix}"
    # 不写版本快照、不动发布时间
    assert db_post.version_snapshots == []
    assert db_post.published_at == datetime(2026, 1, 2, 3, 4, 5)
    assert update_calls, "内联更新后应失效前台缓存"


def test_inline_status_draft_keeps_published_at(inline_setup):
    post_id = inline_setup.post.id

    response = _patch(inline_setup.client, post_id, {"status": "draft"})

    assert response.status_code == 200, response.text
    assert response.json()["post"]["status_label"] == "草稿"

    db_post = inline_setup.db.get(PostModel, post_id)
    inline_setup.db.refresh(db_post)
    assert db_post.status == "draft"
    # 转草稿保留原发布时间，避免误操作丢失
    assert db_post.published_at == datetime(2026, 1, 2, 3, 4, 5)


def test_inline_categories_and_tags_update(inline_setup):
    post_id = inline_setup.post.id
    payload = {
        "category_ids": [inline_setup.category_b.id, inline_setup.category_a.id],
        "tag_names": [" Python ", "python", "后端"],
    }

    response = _patch(inline_setup.client, post_id, payload)

    assert response.status_code == 200, response.text
    data = response.json()["post"]
    assert sorted(data["category_ids"]) == sorted(
        [inline_setup.category_a.id, inline_setup.category_b.id]
    )
    assert sorted(data["tag_names"]) == ["Python", "后端"]

    db_post = inline_setup.db.get(PostModel, post_id)
    inline_setup.db.refresh(db_post)
    assert {category.id for category in db_post.categories} == {
        inline_setup.category_a.id,
        inline_setup.category_b.id,
    }
    assert sorted(tag.name for tag in db_post.tags) == ["Python", "后端"]


def test_inline_excerpt_update_and_clear(inline_setup):
    post_id = inline_setup.post.id

    response = _patch(inline_setup.client, post_id, {"excerpt": "手写摘要"})
    assert response.status_code == 200, response.text
    assert response.json()["post"]["summary"] == "手写摘要"

    cleared = _patch(inline_setup.client, post_id, {"excerpt": ""})
    assert cleared.status_code == 200, cleared.text
    data = cleared.json()["post"]
    assert data["excerpt"] == ""
    # 清空手动摘要后回退到正文自动摘要
    assert data["summary"] == "原始正文"

    db_post = inline_setup.db.get(PostModel, post_id)
    inline_setup.db.refresh(db_post)
    assert (db_post.excerpt or "") == ""


def test_inline_published_at_uses_site_timezone(inline_setup):
    post_id = inline_setup.post.id

    response = _patch(inline_setup.client, post_id, {"published_at": "2026-03-04T05:06"})

    assert response.status_code == 200, response.text
    assert response.json()["post"]["published_at_input"] == "2026-03-04T05:06"

    db_post = inline_setup.db.get(PostModel, post_id)
    inline_setup.db.refresh(db_post)
    assert db_post.published_at == site_local_to_utc_naive(datetime(2026, 3, 4, 5, 6))


def test_inline_update_rejects_empty_title(inline_setup):
    response = _patch(inline_setup.client, inline_setup.post.id, {"title": "   "})

    assert response.status_code == 400
    assert _error_message(response) == "标题不能为空"


def test_inline_update_rejects_unknown_status(inline_setup):
    response = _patch(inline_setup.client, inline_setup.post.id, {"status": "scheduled"})

    assert response.status_code == 400
    assert _error_message(response) == "状态仅支持已发布或草稿"


def test_inline_update_rejects_clearing_published_at_when_published(inline_setup):
    response = _patch(inline_setup.client, inline_setup.post.id, {"published_at": ""})

    assert response.status_code == 400
    assert _error_message(response) == "已发布文章必须保留发布时间"


def test_inline_update_rejects_unknown_category(inline_setup):
    response = _patch(inline_setup.client, inline_setup.post.id, {"category_ids": [999999]})

    assert response.status_code == 400
    assert _error_message(response) == "部分分类不存在，请刷新页面后重试"


def test_inline_update_rejects_categories_for_micro(inline_setup):
    db = inline_setup.db
    micro_format = db.query(Format).filter(Format.slug == "micro").first()
    if micro_format is None:
        micro_format = Format(name="微博", slug="micro")
        db.add(micro_format)
        db.commit()
        db.refresh(micro_format)

    micro_post = PostModel(
        title="微博内容",
        slug=f"micro-{inline_setup.suffix}",
        content_markdown="今天随手记一条",
        content_html="<p>今天随手记一条</p>",
        post_type="post",
        status="published",
        visibility="public",
        published_at=datetime(2026, 1, 2, 3, 4, 5),
        author_id=1,
        version_snapshots=[],
    )
    micro_post.formats.append(micro_format)
    micro_post.categories.append(inline_setup.category_a)
    db.add(micro_post)
    db.commit()
    db.refresh(micro_post)

    response = inline_setup.client.patch(
        _inline_url(micro_post.id),
        json={"category_ids": [inline_setup.category_b.id]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert response.status_code == 400, response.text
    assert "不支持分类" in _error_message(response)


def test_switching_to_micro_clears_existing_categories(inline_setup):
    db = inline_setup.db
    micro_format = db.query(Format).filter(Format.slug == "micro").first()
    if micro_format is None:
        micro_format = Format(name="微博", slug="micro")
        db.add(micro_format)
        db.commit()
        db.refresh(micro_format)

    updated = crud_post.update_post(
        db=db,
        post_id=inline_setup.post.id,
        post=PostUpdate(),
        format_ids=[micro_format.id],
    )

    db.refresh(updated)
    assert updated.categories == []


def test_create_micro_ignores_category_ids(inline_setup):
    db = inline_setup.db
    micro_format = db.query(Format).filter(Format.slug == "micro").first()
    if micro_format is None:
        micro_format = Format(name="微博", slug="micro")
        db.add(micro_format)
        db.commit()
        db.refresh(micro_format)

    created = crud_post.create_post(
        db=db,
        post=PostCreate(
            title="新建微博",
            content_markdown="新建微博正文",
            category_ids=[inline_setup.category_a.id],
        ),
        author_id=1,
        format_ids=[micro_format.id],
    )

    db.refresh(created)
    assert created.categories == []


def test_inline_update_rejects_empty_payload(inline_setup):
    response = _patch(inline_setup.client, inline_setup.post.id, {})

    assert response.status_code == 400
    assert _error_message(response) == "没有需要更新的字段"


def test_inline_update_rejects_page_type(inline_setup):
    page = PostModel(
        title="某个页面",
        slug=f"some-page-{inline_setup.suffix}",
        content_markdown="页面正文",
        content_html="<p>页面正文</p>",
        post_type="page",
        status="published",
        visibility="public",
        published_at=datetime(2026, 1, 2, 3, 4, 5),
        author_id=1,
        version_snapshots=[],
    )
    inline_setup.db.add(page)
    inline_setup.db.commit()
    inline_setup.db.refresh(page)

    response = _patch(inline_setup.client, page.id, {"title": "改名页面"})

    assert response.status_code == 400
    assert _error_message(response) == "该接口仅用于文章"
