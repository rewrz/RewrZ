"""文章兜底封面缓存的有效期、清理与手动刷新测试。"""

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.core.config import settings as app_settings
from rewrz.core.database import get_db
from rewrz.core.security import get_current_user
from rewrz.models.post import Post
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser


_API_URL = "https://example.com/acg/"


def _post(post_id=7, slug="demo", featured_image_url=None, content_markdown="正文", content_html=None):
    return SimpleNamespace(
        id=post_id,
        slug=slug,
        featured_image_url=featured_image_url,
        content_markdown=content_markdown,
        content_html=content_html,
    )


def _cache_index(seed: str, file_name: str, api_url: str = _API_URL, expire_at=None):
    cache_key = main_module._build_article_api_cache_key(api_url, seed)
    return {
        cache_key: {
            "file_name": file_name,
            "api_url": api_url,
            "seed": seed,
            "cached_at": "2026-01-01T00:00:00+00:00",
            "expire_at": expire_at,
        }
    }


def _patch_cache_config(monkeypatch, index: dict):
    config = {
        main_module._ARTICLE_API_CACHE_INDEX_KEY: index,
        "article_card_fallback_source": "api",
        "article_card_api_cache_enabled": True,
        "article_card_api_cache_ttl_minutes": 0,
        "article_card_fallback_api_url": _API_URL,
    }
    monkeypatch.setattr(
        main_module,
        "get_page_config",
        lambda db, key, default: config.get(key, default),
    )
    return config


def test_never_expire_entry_is_reused_without_download(monkeypatch, tmp_path):
    cached_file = tmp_path / "cached.webp"
    cached_file.write_bytes(b"cached-image")
    index = _cache_index("7-demo", "cached.webp", expire_at="2000-01-01T00:00:00+00:00")
    downloads = []
    monkeypatch.setattr(
        main_module,
        "_download_remote_image",
        lambda url: downloads.append(url) or None,
    )

    resolved_url, changed = main_module._resolve_cached_remote_article_image(
        seed_value="7-demo",
        fallback_api_url=_API_URL,
        cache_index=index,
        cache_ttl_minutes=0,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
        download_if_missing=True,
    )

    assert resolved_url == main_module._build_cached_article_image_url(
        "cached.webp", next(iter(index.values()))
    )
    assert "?v=" in resolved_url
    assert changed is False
    assert downloads == []


def test_expired_entry_is_refreshed_when_ttl_enabled(monkeypatch, tmp_path):
    cached_file = tmp_path / "cached.webp"
    cached_file.write_bytes(b"cached-image")
    index = _cache_index("7-demo", "cached.webp", expire_at="2000-01-01T00:00:00+00:00")
    downloads = []
    monkeypatch.setattr(
        main_module,
        "_download_remote_image",
        lambda url: downloads.append(url) or None,
    )

    resolved_url, changed = main_module._resolve_cached_remote_article_image(
        seed_value="7-demo",
        fallback_api_url=_API_URL,
        cache_index=index,
        cache_ttl_minutes=60,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
        download_if_missing=True,
    )

    assert resolved_url.startswith(_API_URL)
    assert changed is False
    assert len(downloads) == 1


def test_cached_cover_url_version_tracks_cached_at():
    base_entry = {"file_name": "cover.webp"}
    first_url = main_module._build_cached_article_image_url(
        "cover.webp", {**base_entry, "cached_at": "2026-01-01T00:00:00+00:00"}
    )
    second_url = main_module._build_cached_article_image_url(
        "cover.webp", {**base_entry, "cached_at": "2026-02-01T00:00:00+00:00"}
    )

    assert first_url.startswith(main_module._ARTICLE_API_CACHE_PUBLIC_PREFIX)
    assert "?v=" in first_url
    assert first_url != second_url
    assert main_module._build_cached_article_image_url("cover.webp", base_entry).endswith("cover.webp")


def test_new_cache_entry_returns_versioned_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main_module,
        "_download_remote_image",
        lambda url: (b"raw-image", "image/jpeg", url),
    )
    monkeypatch.setattr(main_module, "_compress_article_cache_image", lambda payload: b"webp-image")
    cache_index = {}

    resolved_url, changed = main_module._resolve_cached_remote_article_image(
        seed_value="7-demo",
        fallback_api_url=_API_URL,
        cache_index=cache_index,
        cache_ttl_minutes=0,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
    )

    assert changed is True
    entry = next(iter(cache_index.values()))
    assert resolved_url == main_module._build_cached_article_image_url(entry["file_name"], entry)
    assert resolved_url.endswith(f"?v={int(datetime.fromisoformat(entry['cached_at']).timestamp())}")
    assert (tmp_path / entry["file_name"]).exists()


def test_cleanup_keeps_entries_when_never_expire(tmp_path):
    cached_file = tmp_path / "cached.webp"
    cached_file.write_bytes(b"cached-image")
    index = _cache_index("7-demo", "cached.webp", expire_at="2000-01-01T00:00:00+00:00")

    cleaned, changed = main_module._cleanup_article_api_cache(
        index,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
        cache_ttl_minutes=0,
        current_api_url=_API_URL,
    )

    assert changed is False
    assert set(cleaned) == set(index)
    assert cached_file.exists()


def test_cleanup_removes_expired_entries_when_ttl_enabled(tmp_path):
    cached_file = tmp_path / "cached.webp"
    cached_file.write_bytes(b"cached-image")
    index = _cache_index("7-demo", "cached.webp", expire_at="2000-01-01T00:00:00+00:00")

    cleaned, changed = main_module._cleanup_article_api_cache(
        index,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
        cache_ttl_minutes=60,
        current_api_url=_API_URL,
    )

    assert changed is True
    assert cleaned == {}
    assert not cached_file.exists()


def test_cleanup_removes_entries_when_api_url_changed(tmp_path):
    cached_file = tmp_path / "cached.webp"
    cached_file.write_bytes(b"cached-image")
    index = _cache_index("7-demo", "cached.webp")

    cleaned, changed = main_module._cleanup_article_api_cache(
        index,
        cache_dir=tmp_path,
        now_utc=datetime.now(timezone.utc),
        cache_ttl_minutes=0,
        current_api_url="https://example.com/other/",
    )

    assert changed is True
    assert cleaned == {}
    assert not cached_file.exists()


def test_refresh_cover_cache_removes_old_file_and_schedules_prefetch(monkeypatch, tmp_path):
    cached_file = tmp_path / "old.webp"
    cached_file.write_bytes(b"old-image")
    index = _cache_index("7-demo", "old.webp")
    writes = []
    scheduled = []

    _patch_cache_config(monkeypatch, index)
    monkeypatch.setattr(main_module, "_ensure_article_api_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        main_module,
        "_upsert_runtime_setting",
        lambda db, key, value, description: writes.append((key, value)),
    )
    monkeypatch.setattr(
        main_module,
        "_schedule_article_api_cache_prefetch",
        lambda **kwargs: scheduled.append(kwargs) or True,
    )

    result = main_module.refresh_article_cover_cache(None, _post())

    assert result == {"removed": 1, "scheduled": True, "reason": ""}
    assert not cached_file.exists()
    assert writes == [(main_module._ARTICLE_API_CACHE_INDEX_KEY, {})]
    assert scheduled == [
        {"seed_value": "7-demo", "fallback_api_url": _API_URL, "cache_ttl_minutes": 0}
    ]


def test_refresh_cover_cache_ignores_previous_slug_entry(monkeypatch, tmp_path):
    old_file = tmp_path / "old-slug.webp"
    old_file.write_bytes(b"old-image")
    index = _cache_index("7-old-slug", "old-slug.webp")

    _patch_cache_config(monkeypatch, index)
    monkeypatch.setattr(main_module, "_ensure_article_api_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(main_module, "_upsert_runtime_setting", lambda *args: None)
    monkeypatch.setattr(
        main_module,
        "_schedule_article_api_cache_prefetch",
        lambda **kwargs: True,
    )

    result = main_module.refresh_article_cover_cache(
        None,
        _post(slug="new-slug"),
        previous_slug="old-slug",
    )

    assert result["removed"] == 1
    assert not old_file.exists()


def test_refresh_cover_cache_skips_prefetch_when_post_has_cover(monkeypatch, tmp_path):
    scheduled = []
    _patch_cache_config(monkeypatch, {})
    monkeypatch.setattr(main_module, "_ensure_article_api_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        main_module,
        "_schedule_article_api_cache_prefetch",
        lambda **kwargs: scheduled.append(kwargs) or True,
    )

    result = main_module.refresh_article_cover_cache(
        None,
        _post(featured_image_url="https://cdn.example.com/cover.jpg"),
    )

    assert result["scheduled"] is False
    assert "无需预热" in result["reason"]
    assert scheduled == []


# --- 后台手动刷新接口测试 ---

def _build_admin_client(test_db, monkeypatch) -> TestClient:
    """构造已登录的后台测试客户端，复用项目现有后台路由。"""
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    if not main_module.ADMIN_ROUTES_REGISTERED:
        main_module.register_admin_routes()
        main_module.ADMIN_ROUTES_REGISTERED = True

    if test_db.query(DbUser).filter(DbUser.id == 1).first() is None:
        test_db.add(
            DbUser(
                id=1,
                username="admin",
                hashed_password="hashed",
                email="admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
                display_name="管理员",
            )
        )
    existing_keys = {item.key for item in test_db.query(Setting).all()}
    for key, value in {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "https://example.com"},
        "smtp_port": {"value": 587},
    }.items():
        if key not in existing_keys:
            test_db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))
    test_db.commit()

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


def _create_post(test_db, *, post_type: str = "post", slug: str = "refresh-target") -> Post:
    post = Post(
        title="刷新封面缓存",
        slug=f"{slug}-{uuid4().hex[:8]}",
        content_markdown="正文内容",
        content_html="<p>正文内容</p>",
        post_type=post_type,
        status="published",
        visibility="public",
        author_id=1,
    )
    test_db.add(post)
    test_db.commit()
    test_db.refresh(post)
    return post


def _fetch_csrf_token(client: TestClient) -> str:
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    response = client.get(f"{admin_prefix}/settings")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    assert match is not None, "页面中未找到 CSRF 令牌"
    return match.group(1)


def _refresh_url(post_id: int) -> str:
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    return f"{admin_prefix}/api/v1/posts/{post_id}/cover-cache/refresh"


def test_manual_refresh_endpoint_rejects_invalid_csrf_and_unknown_post(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    post = _create_post(test_db)

    try:
        csrf_token = _fetch_csrf_token(client)

        rejected = client.post(
            _refresh_url(post.id),
            headers={"X-CSRF-Token": "invalid-token"},
        )
        assert rejected.status_code == 403

        missing = client.post(
            _refresh_url(99999),
            headers={"X-CSRF-Token": csrf_token},
        )
        assert missing.status_code == 404
        assert "文章不存在" in missing.text

        page = _create_post(test_db, post_type="page", slug="refresh-page")
        page_rejected = client.post(
            _refresh_url(page.id),
            headers={"X-CSRF-Token": csrf_token},
        )
        assert page_rejected.status_code == 404
    finally:
        main_module.app.dependency_overrides.clear()


def test_manual_refresh_endpoint_returns_scheduled_message(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    post = _create_post(test_db)
    calls = []
    monkeypatch.setattr(
        main_module,
        "refresh_article_cover_cache",
        lambda db, target: calls.append(target.id) or {"removed": 1, "scheduled": True, "reason": ""},
    )

    try:
        response = client.post(
            _refresh_url(post.id),
            headers={"X-CSRF-Token": _fetch_csrf_token(client)},
        )
    finally:
        main_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["scheduled"] is True
    assert "稍后访问即可看到新封面" in payload["message"]
    assert calls == [post.id]


def test_manual_refresh_endpoint_returns_removed_message(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    post = _create_post(test_db)
    monkeypatch.setattr(
        main_module,
        "refresh_article_cover_cache",
        lambda db, target: {"removed": 2, "scheduled": False, "reason": ""},
    )

    try:
        response = client.post(
            _refresh_url(post.id),
            headers={"X-CSRF-Token": _fetch_csrf_token(client)},
        )
    finally:
        main_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["removed"] == 2
    assert "已清理 2 份旧封面缓存" in payload["message"]
