"""
版本快照回归测试。

覆盖：
- 正文保存后快照真正落库（JSON 列必须整体赋值才能被追踪）
- 仅改元数据不产生快照
- 重复内容不产生重复快照
- Markdown / HTML 两种模式的恢复都正确
- 页面类型（post_type=page）同样生效
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.api import posts as posts_api
from rewrz.core.database import get_db
from rewrz.core.security import get_current_user
from rewrz.crud import post as crud_post
from rewrz.crud.post import SNAPSHOT_LIMIT
from rewrz.models.post import Post as PostModel
from rewrz.models.user import User as DbUser
from rewrz.schemas import PostUpdate


def _build_client(test_db, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True
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


@pytest.fixture()
def snapshot_client(test_db, monkeypatch):
    client = _build_client(test_db, monkeypatch)
    try:
        yield client
    finally:
        main_module.app.dependency_overrides.clear()


def _make_post(
    test_db,
    *,
    post_type: str = "post",
    content_markdown: str = "第一版正文",
    content_html: str = "",
) -> PostModel:
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

    suffix = uuid4().hex[:8]
    post = PostModel(
        title="快照测试",
        slug=f"snapshot-{suffix}",
        content_markdown=content_markdown,
        content_html=content_html,
        post_type=post_type,
        status="draft",
        visibility="public",
        author_id=1,
        version_snapshots=[],
    )
    test_db.add(post)
    test_db.commit()
    test_db.refresh(post)
    return post


def _update_content(test_db, post, markdown: str, html: str = "", editor_mode: str = "markdown"):
    return crud_post.update_post(
        test_db,
        post.id,
        PostUpdate(content_markdown=markdown, content_html=html, editor_mode=editor_mode),
    )


def test_content_update_persists_snapshot_across_sessions(test_db, test_engine):
    post = _make_post(test_db)

    _update_content(test_db, post, "第二版正文")
    test_db.refresh(post)

    assert len(post.version_snapshots) == 1
    entry = post.version_snapshots[0]
    assert entry["content_markdown"] == "第一版正文"
    assert entry["content_html"] == ""
    assert entry["editor_mode"] == "markdown"
    assert entry["timestamp"]

    # 换一个会话读取，确认快照真的写入了数据库，而不是只停留在内存
    other_db = sessionmaker(bind=test_engine)()
    try:
        row = other_db.get(PostModel, post.id)
        other_db.refresh(row)
        assert len(row.version_snapshots) == 1
        assert row.version_snapshots[0]["content_markdown"] == "第一版正文"
    finally:
        other_db.close()


def test_metadata_only_update_does_not_create_snapshot(test_db):
    post = _make_post(test_db)

    crud_post.update_post(test_db, post.id, PostUpdate(title="只改标题"))
    test_db.refresh(post)

    assert post.title == "只改标题"
    assert post.version_snapshots == []


def test_same_content_update_skips_duplicate_snapshot(test_db):
    post = _make_post(test_db)

    _update_content(test_db, post, "第二版正文")
    test_db.refresh(post)
    assert len(post.version_snapshots) == 1

    # 正文没有变化时不应再占用快照名额
    _update_content(test_db, post, "第二版正文")
    test_db.refresh(post)
    assert len(post.version_snapshots) == 1


def test_snapshot_limit_keeps_latest_entries(test_db):
    post = _make_post(test_db)

    for version in range(1, SNAPSHOT_LIMIT + 3):
        _update_content(test_db, post, f"第{version}版正文")

    test_db.refresh(post)
    assert len(post.version_snapshots) == SNAPSHOT_LIMIT
    # 最新快照应保存上一版正文
    assert post.version_snapshots[0]["content_markdown"] == f"第{SNAPSHOT_LIMIT + 1}版正文"


def test_html_mode_snapshot_and_restore(snapshot_client, test_db):
    post = _make_post(test_db, content_markdown="", content_html="<p>第一版HTML</p>")

    _update_content(test_db, post, "", html="<p>第二版HTML</p>", editor_mode="html")
    test_db.refresh(post)
    assert post.version_snapshots[0]["editor_mode"] == "html"
    assert post.version_snapshots[0]["content_html"] == "<p>第一版HTML</p>"
    assert post.version_snapshots[0]["content_markdown"] == ""

    listed = snapshot_client.get(f"/api/v1/posts/{post.id}/snapshots/json")
    assert listed.status_code == 200, listed.text
    snapshot = listed.json()["snapshots"][0]
    assert snapshot["editor_mode"] == "html"
    assert "第一版HTML" in snapshot["content_html"]

    restored = snapshot_client.post(f"/api/v1/posts/{post.id}/snapshots/0/restore")
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["editor_mode"] == "html"
    assert body["new_html"] == "<p>第一版HTML</p>"

    test_db.refresh(post)
    assert post.content_html == "<p>第一版HTML</p>"
    assert post.content_markdown == ""
    # 恢复前的第二版内容被保存为恢复点
    assert post.version_snapshots[0]["restore_point"] is True
    assert post.version_snapshots[0]["content_html"] == "<p>第二版HTML</p>"


def test_markdown_mode_restore_through_api(snapshot_client, test_db):
    post = _make_post(test_db, content_markdown="第一版正文")

    _update_content(test_db, post, "第二版正文")

    restored = snapshot_client.post(f"/api/v1/posts/{post.id}/snapshots/0/restore")
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["editor_mode"] == "markdown"
    assert body["new_content"] == "第一版正文"

    test_db.refresh(post)
    assert post.content_markdown == "第一版正文"
    assert post.content_html == ""


def test_page_type_snapshot_works(test_db):
    page = _make_post(test_db, post_type="page", content_markdown="页面第一版")

    _update_content(test_db, page, "页面第二版")
    test_db.refresh(page)

    assert len(page.version_snapshots) == 1
    assert page.version_snapshots[0]["content_markdown"] == "页面第一版"


def test_compare_snapshot_returns_diff(snapshot_client, test_db):
    post = _make_post(test_db, content_markdown="第一行\n第二行")

    _update_content(test_db, post, "第一行\n第二行修改")

    response = snapshot_client.get(f"/api/v1/posts/{post.id}/snapshots/0/compare?compare_with=current")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["additions"] >= 1
    assert body["summary"]["deletions"] >= 1
    assert any(line["type"] == "addition" for line in body["diff"])
    assert any(line["type"] == "deletion" for line in body["diff"])


def test_batch_clear_snapshots_across_posts_and_pages(snapshot_client, test_db):
    post = _make_post(test_db)
    page = _make_post(test_db, post_type="page", content_markdown="页面第一版")
    empty_post = _make_post(test_db, content_markdown="没有快照的内容")

    for version in range(1, 4):
        _update_content(test_db, post, f"第{version}版正文")
    _update_content(test_db, page, "页面第二版")

    response = snapshot_client.post(
        f"{main_module.settings.ADMIN_PATH.rstrip('/')}/api/v1/posts/batch-clear-snapshots",
        json={"post_ids": [post.id, page.id, empty_post.id]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["cleared_count"] == 2
    assert body["deleted_snapshot_count"] == 4

    test_db.refresh(post)
    test_db.refresh(page)
    test_db.refresh(empty_post)
    assert post.version_snapshots == []
    assert page.version_snapshots == []
    assert empty_post.version_snapshots == []


def test_batch_delete_and_single_delete_snapshots(snapshot_client, test_db):
    post = _make_post(test_db)
    for version in range(1, 5):
        _update_content(test_db, post, f"第{version}版正文")

    test_db.refresh(post)
    assert len(post.version_snapshots) == 4

    listed = snapshot_client.get(f"/api/v1/posts/{post.id}/snapshots/json")
    assert listed.status_code == 200, listed.text
    assert listed.json()["snapshot_limit"] == SNAPSHOT_LIMIT

    # 批量删除中间两条，索引不会因为删除而错位
    batch = snapshot_client.post(
        f"/api/v1/posts/{post.id}/snapshots/batch-delete",
        json={"indices": [1, 2]},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["deleted_count"] == 2

    test_db.refresh(post)
    assert len(post.version_snapshots) == 2
    assert [item["content_markdown"] for item in post.version_snapshots] == ["第3版正文", "第一版正文"]

    # 单条删除
    single = snapshot_client.delete(f"/api/v1/posts/{post.id}/snapshots/0")
    assert single.status_code == 200, single.text

    test_db.refresh(post)
    assert len(post.version_snapshots) == 1
    assert post.version_snapshots[0]["content_markdown"] == "第一版正文"


def test_explicit_snapshot_list_cannot_exceed_limit(test_db):
    post = _make_post(test_db)

    oversized = [
        {
            "timestamp": f"2026-01-01T00:00:{index:02d}",
            "editor_mode": "markdown",
            "content_markdown": f"历史正文{index}",
            "content_html": "",
        }
        for index in range(SNAPSHOT_LIMIT + 3)
    ]
    crud_post.update_post(test_db, post.id, PostUpdate(version_snapshots=oversized))

    test_db.refresh(post)
    assert len(post.version_snapshots) == SNAPSHOT_LIMIT
    assert post.version_snapshots[0]["content_markdown"] == "历史正文0"


def test_snapshots_html_page_renders(snapshot_client, test_db):
    post = _make_post(test_db)
    _update_content(test_db, post, "第二版正文")

    response = snapshot_client.get(f"/api/v1/posts/{post.id}/snapshots")
    assert response.status_code == 200, response.text
    assert "历史快照" in response.text
