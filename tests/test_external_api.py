import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.api import media as media_runtime_api
from rewrz.crud import post as crud_post
from rewrz.core.api_keys import build_api_key_plaintext, hash_api_key_secret
from rewrz.core.database import Base
from rewrz.core.database import get_db
from rewrz.core.security import create_access_token
from rewrz.models import ApiKey, Category, Format, Post, Setting, Tag, User as DbUser


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _seed_external_api_basics(db):
    user = db.query(DbUser).filter(DbUser.id == 1).first()
    if user is None:
        user = DbUser(
            id=1,
            username="admin",
            hashed_password="hashed",
            email="admin@example.com",
            is_active=True,
            role="super_admin",
            use_gravatar="auto",
        )
        db.add(user)

    if db.query(Format).filter(Format.slug == "article").first() is None:
        db.add(Format(name="标准文章", slug="article"))
    if db.query(Format).filter(Format.slug == "micro").first() is None:
        db.add(Format(name="微博", slug="micro"))
    if db.query(Category).filter(Category.slug == "default-category").first() is None:
        db.add(Category(name="默认分类", slug="default-category"))
    if db.query(Tag).filter(Tag.slug == "default-tag").first() is None:
        db.add(Tag(name="默认标签", slug="default-tag"))
    db.commit()
    return user


def _build_client(monkeypatch, tmp_path):
    _set_installation_complete(monkeypatch, True)
    db_path = tmp_path / f"external-api-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main_module.app), testing_session_local, engine


def _create_api_key(session_factory, *, access_level: str = "manager", status: str = "active"):
    with session_factory() as db:
        _seed_external_api_basics(db)
        key_prefix, plain_token = build_api_key_plaintext()
        db_api_key = ApiKey(
            name="外部测试 Key",
            key_prefix=key_prefix,
            secret_hash=hash_api_key_secret(plain_token),
            access_level=access_level,
            status=status,
            created_by_user_id=1,
        )
        db.add(db_api_key)
        db.commit()
        db.refresh(db_api_key)
        return int(db_api_key.id), plain_token


def _auth_headers(plain_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {plain_token}"}


def _unique_text(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _extract_csrf_token(response_text: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response_text)
    assert match is not None, "页面中未找到 CSRF 令牌"
    return match.group(1)


def test_external_posts_requires_bearer_key(monkeypatch, tmp_path):
    client, _, engine = _build_client(monkeypatch, tmp_path)
    try:
        response = client.get("/api/external/v1/posts")
        assert response.status_code == 401
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_posts_read_works_with_read_only_key(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, plain_token = _create_api_key(session_factory, access_level="read_only")
    try:
        response = client.get(
            "/api/external/v1/posts",
            headers=_auth_headers(plain_token),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert "items" in payload
        assert payload["pagination"]["page"] == 1
        assert payload["pagination"]["per_page"] == 20
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_post_create_forbidden_for_read_only_key(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, plain_token = _create_api_key(session_factory, access_level="read_only")
    try:
        response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(plain_token),
            json={
                "title": "外部文章",
                "content_markdown": "内容",
                "status": "draft",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "外部 API 权限不足"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_post_create_works_for_manager_key(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, plain_token = _create_api_key(session_factory, access_level="manager")
    try:
        response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(plain_token),
            json={
                "title": "外部文章",
                "content_markdown": "内容",
                "status": "draft",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["title"] == "外部文章"
        assert payload["data"]["post_type"] == "post"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_api_rejects_disabled_key(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, plain_token = _create_api_key(session_factory, access_level="manager", status="disabled")
    try:
        response = client.get(
            "/api/external/v1/posts",
            headers=_auth_headers(plain_token),
        )
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "API Key 已停用"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_pages_read_and_post_type_guard_work(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    _, read_only_token = _create_api_key(session_factory, access_level="read_only")
    post_title = _unique_text("文章型内容")
    page_title = _unique_text("页面型内容")
    try:
        post_response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(manager_token),
            json={
                "title": post_title,
                "content_markdown": "这是文章",
                "status": "draft",
            },
        )
        assert post_response.status_code == 200
        post_id = post_response.json()["data"]["id"]

        page_response = client.post(
            "/api/external/v1/pages",
            headers=_auth_headers(manager_token),
            json={
                "title": page_title,
                "content_markdown": "这是页面",
                "status": "draft",
                "page_template": "default",
            },
        )
        assert page_response.status_code == 200
        page_payload = page_response.json()["data"]
        page_id = page_payload["id"]
        assert page_payload["post_type"] == "page"
        assert page_payload["page_template"] == "default"

        list_response = client.get(
            "/api/external/v1/pages",
            headers=_auth_headers(read_only_token),
        )
        assert list_response.status_code == 200
        page_ids = [item["id"] for item in list_response.json()["items"]]
        assert page_id in page_ids
        assert post_id not in page_ids

        get_response = client.get(
            f"/api/external/v1/pages/{page_id}",
            headers=_auth_headers(read_only_token),
        )
        assert get_response.status_code == 200
        assert get_response.json()["data"]["title"] == page_title

        wrong_type_response = client.get(
            f"/api/external/v1/pages/{post_id}",
            headers=_auth_headers(read_only_token),
        )
        assert wrong_type_response.status_code == 404
        assert wrong_type_response.json()["error"]["message"] == "页面不存在"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_posts_permission_levels_cover_publish_and_delete(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, writer_token = _create_api_key(session_factory, access_level="writer")
    _, publisher_token = _create_api_key(session_factory, access_level="publisher")
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    draft_title = _unique_text("写手草稿文章")
    published_title = _unique_text("发布者文章")
    try:
        writer_publish_response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(writer_token),
            json={
                "title": _unique_text("写手发布尝试"),
                "content_markdown": "无权直接发布",
                "status": "published",
            },
        )
        assert writer_publish_response.status_code == 403
        assert writer_publish_response.json()["error"]["message"] == "外部 API 权限不足"

        writer_draft_response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(writer_token),
            json={
                "title": draft_title,
                "content_markdown": "先保存为草稿",
                "status": "draft",
            },
        )
        assert writer_draft_response.status_code == 200
        writer_post_id = writer_draft_response.json()["data"]["id"]

        writer_patch_publish = client.patch(
            f"/api/external/v1/posts/{writer_post_id}",
            headers=_auth_headers(writer_token),
            json={"status": "published"},
        )
        assert writer_patch_publish.status_code == 403
        assert writer_patch_publish.json()["error"]["message"] == "外部 API 权限不足"

        publisher_create_response = client.post(
            "/api/external/v1/posts",
            headers=_auth_headers(publisher_token),
            json={
                "title": published_title,
                "content_markdown": "发布者可直接发布",
                "status": "published",
            },
        )
        assert publisher_create_response.status_code == 200
        publisher_payload = publisher_create_response.json()["data"]
        publisher_post_id = publisher_payload["id"]
        assert publisher_payload["status"] == "published"
        assert publisher_payload["published_at"] is not None

        publisher_delete_response = client.delete(
            f"/api/external/v1/posts/{publisher_post_id}",
            headers=_auth_headers(publisher_token),
        )
        assert publisher_delete_response.status_code == 403
        assert publisher_delete_response.json()["error"]["message"] == "外部 API 权限不足"

        manager_delete_response = client.delete(
            f"/api/external/v1/posts/{publisher_post_id}",
            headers=_auth_headers(manager_token),
        )
        assert manager_delete_response.status_code == 200
        assert manager_delete_response.json()["success"] is True
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_pages_permission_levels_cover_publish_and_delete(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, writer_token = _create_api_key(session_factory, access_level="writer")
    _, publisher_token = _create_api_key(session_factory, access_level="publisher")
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    draft_title = _unique_text("写手草稿页面")
    published_title = _unique_text("发布者页面")
    try:
        writer_create_response = client.post(
            "/api/external/v1/pages",
            headers=_auth_headers(writer_token),
            json={
                "title": draft_title,
                "content_markdown": "草稿页面内容",
                "status": "draft",
                "page_template": "default",
            },
        )
        assert writer_create_response.status_code == 200
        writer_page_id = writer_create_response.json()["data"]["id"]

        writer_publish_response = client.patch(
            f"/api/external/v1/pages/{writer_page_id}",
            headers=_auth_headers(writer_token),
            json={"status": "published"},
        )
        assert writer_publish_response.status_code == 403
        assert writer_publish_response.json()["error"]["message"] == "外部 API 权限不足"

        publisher_create_response = client.post(
            "/api/external/v1/pages",
            headers=_auth_headers(publisher_token),
            json={
                "title": published_title,
                "content_markdown": "发布者页面内容",
                "status": "published",
                "page_template": "default",
            },
        )
        assert publisher_create_response.status_code == 200
        publisher_page_id = publisher_create_response.json()["data"]["id"]

        publisher_delete_response = client.delete(
            f"/api/external/v1/pages/{publisher_page_id}",
            headers=_auth_headers(publisher_token),
        )
        assert publisher_delete_response.status_code == 403
        assert publisher_delete_response.json()["error"]["message"] == "外部 API 权限不足"

        manager_delete_response = client.delete(
            f"/api/external/v1/pages/{publisher_page_id}",
            headers=_auth_headers(manager_token),
        )
        assert manager_delete_response.status_code == 200
        assert manager_delete_response.json()["success"] is True
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_taxonomy_endpoints_require_auth_and_return_seeded_data(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, read_only_token = _create_api_key(session_factory, access_level="read_only")
    try:
        for endpoint in ("/api/external/v1/categories", "/api/external/v1/tags"):
            unauthorized = client.get(endpoint)
            assert unauthorized.status_code == 401
            assert unauthorized.json()["error"]["message"] == "缺少 API Key"

        categories_response = client.get(
            "/api/external/v1/categories",
            headers=_auth_headers(read_only_token),
        )
        assert categories_response.status_code == 200
        categories_payload = categories_response.json()["items"]
        assert any(item["slug"] == "default-category" for item in categories_payload)

        tags_response = client.get(
            "/api/external/v1/tags",
            headers=_auth_headers(read_only_token),
        )
        assert tags_response.status_code == 200
        tags_payload = tags_response.json()["items"]
        assert any(item["slug"] == "default-tag" for item in tags_payload)
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_media_upload_permissions_and_validation(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, read_only_token = _create_api_key(session_factory, access_level="read_only")
    _, writer_token = _create_api_key(session_factory, access_level="writer")
    monkeypatch.setattr(media_runtime_api, "UPLOAD_ROOT", tmp_path.resolve())
    Path(media_runtime_api.UPLOAD_ROOT).mkdir(parents=True, exist_ok=True)
    try:
        forbidden_response = client.post(
            "/api/external/v1/media",
            headers=_auth_headers(read_only_token),
            files={"file": ("forbidden.md", "# 外部附件".encode("utf-8"), "text/markdown")},
        )
        assert forbidden_response.status_code == 403
        assert forbidden_response.json()["error"]["message"] == "外部 API 权限不足"

        invalid_folder_response = client.post(
            "/api/external/v1/media",
            headers=_auth_headers(writer_token),
            data={"target_folder": "../escape"},
            files={"file": ("invalid.md", "# 非法目录".encode("utf-8"), "text/markdown")},
        )
        assert invalid_folder_response.status_code == 400
        assert invalid_folder_response.json()["error"]["message"] == "文件夹路径不合法"

        success_response = client.post(
            "/api/external/v1/media",
            headers=_auth_headers(writer_token),
            data={
                "title": "外部附件",
                "target_folder": "external-tests",
            },
            files={"file": ("upload.md", "# 外部 API 媒体上传".encode("utf-8"), "text/markdown")},
        )
        assert success_response.status_code == 200
        payload = success_response.json()["data"]
        assert payload["title"] == "外部附件"
        assert payload["file_type"] == "document"
        assert payload["folder"] == "external-tests"
        assert payload["url"].startswith("/media/external-tests/")
        assert payload["uploaded_by_id"] == 1
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_posts_list_supports_pagination_contract(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    try:
        for index in range(3):
            response = client.post(
                "/api/external/v1/posts",
                headers=_auth_headers(manager_token),
                json={
                    "title": _unique_text(f"分页文章{index}"),
                    "content_markdown": "分页内容",
                    "status": "draft",
                },
            )
            assert response.status_code == 200

        page_one = client.get(
            "/api/external/v1/posts?page=1&per_page=2",
            headers=_auth_headers(manager_token),
        )
        assert page_one.status_code == 200
        payload = page_one.json()
        assert payload["success"] is True
        assert len(payload["items"]) == 2
        assert payload["pagination"] == {
            "page": 1,
            "per_page": 2,
            "count": 2,
            "has_next": True,
        }

        page_two = client.get(
            "/api/external/v1/posts?page=2&per_page=2",
            headers=_auth_headers(manager_token),
        )
        assert page_two.status_code == 200
        assert page_two.json()["pagination"]["page"] == 2
        assert page_two.json()["pagination"]["per_page"] == 2
        assert page_two.json()["pagination"]["count"] == 1
        assert page_two.json()["pagination"]["has_next"] is False
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_posts_and_pages_return_not_found_for_missing_objects(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    try:
        missing_post = client.get(
            "/api/external/v1/posts/999999",
            headers=_auth_headers(manager_token),
        )
        assert missing_post.status_code == 404
        assert missing_post.json()["error"]["message"] == "文章不存在"

        missing_page = client.patch(
            "/api/external/v1/pages/999999",
            headers=_auth_headers(manager_token),
            json={"title": "不存在"},
        )
        assert missing_page.status_code == 404
        assert missing_page.json()["error"]["message"] == "页面不存在"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_external_api_invalid_params_use_validation_error_contract(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    _, manager_token = _create_api_key(session_factory, access_level="manager")
    try:
        response = client.get(
            "/api/external/v1/posts?page=0&per_page=200",
            headers=_auth_headers(manager_token),
        )
        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["message"] == "请求参数验证失败"
        assert payload["error"]["details"]
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_frontend_quick_post_public_path_still_works_with_login_and_csrf(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    with session_factory() as db:
        seeded_user = _seed_external_api_basics(db)
        seeded_user.display_name = "终极改写"
        db.commit()

    try:
        access_token = create_access_token({"sub": "1"})
        client.cookies.set("access_token", access_token)
        page_response = client.get("/formats/micro")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            "/api/v1/posts/quick",
            data={
                "content": "前台快捷动态里#测试#继续@admin",
                "media_items": "[]",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["media_count"] == 0
        assert payload["post_url"].startswith("/micro/")

        created_slug = payload["post_url"].rsplit("/", 1)[-1]
        with session_factory() as db:
            created_post = db.query(Post).filter(Post.slug == created_slug).first()
            assert created_post is not None
            assert "#测试" not in (created_post.content_markdown or "")
            assert "@admin" in (created_post.content_markdown or "")
            assert "前台快捷动态里继续@admin" in (created_post.content_markdown or "")
            assert any(tag.slug == "ce-shi" for tag in created_post.tags)
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_frontend_quick_post_preview_links_display_name_mentions(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    with session_factory() as db:
        seeded_user = _seed_external_api_basics(db)
        seeded_user.display_name = "终极改写"
        db.commit()

    try:
        access_token = create_access_token({"sub": "1"})
        client.cookies.set("access_token", access_token)
        page_response = client.get("/formats/micro")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            "/api/v1/posts/quick/preview",
            data={
                "content": "句中#测试#继续@终极改写",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert "#测试" not in payload["html"]
        assert '@终极改写</a>' in payload["html"]
        assert 'href="/authors/admin"' in payload["html"]
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_frontend_quick_post_preview_prefers_external_mention_mapping(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    with session_factory() as db:
        seeded_user = _seed_external_api_basics(db)
        seeded_user.display_name = "终极改写"
        setting = Setting(
            key="micro_mention_links_json",
            value={"value": '{"终极改写":"https://weibo.example.com/u/rewrz"}'},
            description="外站映射",
            category="content",
            type="json",
        )
        db.add(setting)
        db.commit()

    try:
        access_token = create_access_token({"sub": "1"})
        client.cookies.set("access_token", access_token)
        page_response = client.get("/formats/micro")
        assert page_response.status_code == 200
        csrf_token = _extract_csrf_token(page_response.text)

        response = client.post(
            "/api/v1/posts/quick/preview",
            data={
                "content": "测试 @终极改写",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert 'href="https://weibo.example.com/u/rewrz"' in payload["html"]
        assert 'href="/authors/admin"' not in payload["html"]
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_delete_post_cleans_stale_views_metric(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    del client
    try:
        with session_factory() as db:
            user = _seed_external_api_basics(db)
            micro_format = db.query(Format).filter(Format.slug == "micro").first()
            post = Post(
                title="待删除微博",
                slug="to-delete-micro",
                content_markdown="正文",
                content_html="<p>正文</p>",
                excerpt="",
                post_type="post",
                status="published",
                visibility="public",
                author_id=user.id,
                published_at=datetime(2026, 6, 2, 20, 0, 0),
                formats=[micro_format],
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            db.add(
                Setting(
                    key=f"post_views_count_{post.id}",
                    value={"value": 164},
                    description="test views",
                    category="post_metrics",
                    type="integer",
                )
            )
            db.commit()

            crud_post.delete_post(db, post.id)

            deleted_post = db.query(Post).filter(Post.id == post.id).first()
            deleted_metric = db.query(Setting).filter(Setting.key == f"post_views_count_{post.id}").first()
            assert deleted_post is None
            assert deleted_metric is None
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_format_archive_page_uses_cached_stats_snapshot(monkeypatch, tmp_path):
    client, testing_session_local, engine = _build_client(monkeypatch, tmp_path)
    try:
        with testing_session_local() as db:
            fmt = Format(name="微博", slug="micro")
            if db.query(Format).filter(Format.slug == "micro").first() is None:
                db.add(fmt)
                db.flush()
            else:
                fmt = db.query(Format).filter(Format.slug == "micro").first()

            author = db.query(DbUser).filter(DbUser.id == 1).first()
            if author is None:
                author = DbUser(
                    id=1,
                    username="admin",
                    hashed_password="hashed",
                    email="admin@example.com",
                    is_active=True,
                    role="super_admin",
                    use_gravatar="auto",
                    token_version=1,
                )
                db.add(author)
                db.flush()

            post = Post(
                title="缓存微博",
                slug="cached-micro",
                content_markdown="hello",
                content_html="<p>hello</p>",
                excerpt="hello",
                post_type="post",
                status="published",
                visibility="public",
                author_id=author.id,
                published_at=datetime(2026, 5, 1, 10, 0, 0),
                formats=[fmt],
            )
            db.add(post)
            db.commit()

        from rewrz.core import public_metrics_cache

        cache_key = public_metrics_cache.build_format_archive_cache_key("micro")
        cached_payload = {
            "micro_interaction_count": 77,
            "format_tag_topic_count": 5,
            "format_category_topic_count": 0,
            "format_hot_tags": [{"slug": "hot", "name": "热点", "heat_score": 100, "count": 1}],
            "checked_at_iso": datetime.now().astimezone().isoformat(),
            "checked_at": "2026-05-29 12:00:00 UTC",
            "cache_hit": False,
        }
        with testing_session_local() as db:
            setting = db.query(Setting).filter(Setting.key == cache_key).first()
            if setting is None:
                db.add(Setting(key=cache_key, value={"value": cached_payload}, description="test cache"))
            else:
                setting.value = {"value": cached_payload}
            db.commit()

        def fail_micro_interaction(*args, **kwargs):
            raise AssertionError("缓存命中时不应重新计算微博互动统计")

        from rewrz.api import public_pages as public_pages_module

        monkeypatch.setattr(public_pages_module, "build_micro_interaction_count", fail_micro_interaction)
        response = client.get("/formats/micro")
        assert response.status_code == 200
        assert "77" in response.text
        assert "热点" in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()
