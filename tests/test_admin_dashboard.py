from __future__ import annotations

import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.api import admin_dashboard as admin_dashboard_api
from rewrz.core.config import settings as app_settings
from rewrz.core.cache import clear_cache, cache_key_for_setting
from rewrz.core.database import get_db
from rewrz.core.security import get_current_user
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser


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


def _seed_admin_basics(db) -> DbUser:
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
            display_name="管理员",
        )
        db.add(user)

    existing_keys = {item.key for item in db.query(Setting).all()}
    default_settings = {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "https://example.com"},
    }
    for key, value in default_settings.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))

    db.commit()
    db.refresh(user)
    return user


def _login_user_override() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )


def _build_admin_client(test_db, monkeypatch) -> TestClient:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    _seed_admin_basics(test_db)
    main_module.app.dependency_overrides[get_db] = lambda: test_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app)


def test_dashboard_site_health_uses_cached_snapshot_without_rescanning(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    call_count = {"value": 0}

    def fake_media_stats():
        call_count["value"] += 1
        return 7, 3.5

    monkeypatch.setattr(admin_dashboard_api, "_safe_media_stats", fake_media_stats)

    try:
        first = client.get(f"{admin_prefix}/api/v1/dashboard/site-health")
        assert first.status_code == 200
        assert "3.5 MB / 7 文件" in first.text
        assert call_count["value"] == 1

        second = client.get(f"{admin_prefix}/api/v1/dashboard/site-health")
        assert second.status_code == 200
        assert "3.5 MB / 7 文件" in second.text
        assert call_count["value"] == 1
        assert "缓存命中" in second.text
    finally:
        main_module.app.dependency_overrides.clear()


def test_dashboard_site_health_refreshes_when_cache_expired(test_db, monkeypatch):
    test_db.query(Setting).filter(Setting.key == admin_dashboard_api.SITE_HEALTH_CACHE_KEY).delete()
    test_db.commit()
    clear_cache(cache_key_for_setting(admin_dashboard_api.SITE_HEALTH_CACHE_KEY))

    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = app_settings.ADMIN_PATH.rstrip("/")
    call_count = {"value": 0}

    def fake_media_stats():
        call_count["value"] += 1
        return 2, 1.25

    monkeypatch.setattr(admin_dashboard_api, "_safe_media_stats", fake_media_stats)

    try:
        first = client.get(f"{admin_prefix}/api/v1/dashboard/site-health")
        assert first.status_code == 200
        assert call_count["value"] == 1

        cache_setting = test_db.query(Setting).filter(Setting.key == admin_dashboard_api.SITE_HEALTH_CACHE_KEY).one()
        cached_value = dict(cache_setting.value)
        cached_payload = dict(cached_value.get("value", {}))
        cached_payload["checked_at_iso"] = "2000-01-01T00:00:00+00:00"
        cache_setting.value = {"value": cached_payload}
        test_db.commit()

        second = client.get(f"{admin_prefix}/api/v1/dashboard/site-health")
        assert second.status_code == 200
        assert call_count["value"] == 2
        assert "实时扫描" in second.text
    finally:
        main_module.app.dependency_overrides.clear()
