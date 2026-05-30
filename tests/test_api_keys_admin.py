import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.core.database import get_db
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser
from rewrz.core.security import get_current_user


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


def _seed_admin_basics(db) -> None:
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
    for key, value in {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "https://example.com"},
    }.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))

    db.commit()


def _login_user_override() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="admin",
        email="admin@example.com",
        role="super_admin",
        is_active=True,
        use_gravatar="auto",
    )


def _extract_csrf_token(response_text: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def _build_admin_client(test_db, monkeypatch) -> TestClient:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    _seed_admin_basics(test_db)
    main_module.app.dependency_overrides[get_db] = lambda: test_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app)


def test_api_keys_admin_page_exists(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.get(f"{admin_prefix}/api-keys")
        assert response.status_code == 200
        assert "API Key 管理" in response.text
    finally:
        main_module.app.dependency_overrides.clear()


def test_api_keys_admin_create_returns_plain_token(test_db, monkeypatch):
    client = _build_admin_client(test_db, monkeypatch)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/api-keys")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/api-keys",
            data={
                "name": "测试 Key",
                "access_level": "writer",
                "notes": "用于测试",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["plain_token"].startswith("rwz_")
    finally:
        main_module.app.dependency_overrides.clear()
