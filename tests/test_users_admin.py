import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core import admin_security
from rewrz.core.database import Base, get_db
from rewrz.core.security import create_access_token, get_current_user, get_password_hash, verify_password
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


def _seed_admin_basics(db) -> None:
    existing_admin = db.query(DbUser).filter(DbUser.id == 1).first()
    if existing_admin is None:
        db.add(
            DbUser(
                id=1,
                username="admin",
                hashed_password=get_password_hash("adminpass123"),
                email="admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
                display_name="管理员",
                token_version=1,
            )
        )

    existing_editor = db.query(DbUser).filter(DbUser.id == 2).first()
    if existing_editor is None:
        db.add(
            DbUser(
                id=2,
                username="editor",
                hashed_password=get_password_hash("editorpass123"),
                email="editor@example.com",
                is_active=True,
                role="admin",
                use_gravatar="auto",
                display_name="编辑",
                token_version=1,
            )
        )

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


def _build_admin_client(monkeypatch, tmp_path) -> tuple[TestClient, sessionmaker, object]:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    db_path = tmp_path / Path(f"users-admin-{uuid4().hex}.db")
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

    with testing_session_local() as db:
        _seed_admin_basics(db)

    main_module.app.dependency_overrides[get_db] = override_get_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app), testing_session_local, engine


def test_users_admin_page_lists_managed_users(monkeypatch, tmp_path):
    client, _, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.get(f"{admin_prefix}/users")
        assert response.status_code == 200
        assert "后台用户列表" in response.text
        assert "editor@example.com" in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_admin_api_requires_login_returns_json_unauthorized(monkeypatch, tmp_path):
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    client = TestClient(main_module.app)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    response = client.post(f"{admin_prefix}/api/v1/users/2/status", data={"is_active": "false", "csrf_token": "x"})
    assert response.status_code == 401
    assert response.headers.get("content-type", "").startswith("application/json")
    payload = response.json()
    assert payload["error"]["status_code"] == 401


def test_users_admin_page_shows_recent_activity_summary(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        with session_factory() as db:
            admin_security.record_admin_user_action(
                db,
                event="role_updated",
                actor_user_id=1,
                actor_username="admin",
                target_user_id=2,
                target_username="editor",
                ip_address="127.0.0.1",
                detail={"role": "super_admin"},
            )

        response = client.get(f"{admin_prefix}/users")
        assert response.status_code == 200
        assert "最近活动" in response.text
        assert "角色已更新" in response.text
        assert "角色切换为 super_admin" in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_can_disable_other_user(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users/2/status",
            data={"is_active": "false", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.id == 2).first()
            assert user is not None
            assert user.is_active is False
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_cannot_disable_current_super_admin(monkeypatch, tmp_path):
    client, _, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users/1/status",
            data={"is_active": "false", "csrf_token": csrf_token},
        )
        assert response.status_code == 400
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_can_update_role_for_other_user(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users/2/role",
            data={"role": "super_admin", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.id == 2).first()
            assert user is not None
            assert user.role == "super_admin"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_super_admin_can_create_admin_user(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users",
            data={
                "username": "newadmin",
                "email": "newadmin@example.com",
                "password": "newadmin123",
                "role": "admin",
                "display_name": "新管理员",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.username == "newadmin").first()
            assert user is not None
            assert user.email == "newadmin@example.com"
            assert user.role == "admin"
            assert verify_password("newadmin123", user.hashed_password)
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_can_reset_password(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users/2/password",
            data={"password": "newpass123", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.id == 2).first()
            assert user is not None
            assert verify_password("newpass123", user.hashed_password)
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_can_force_logout_other_user(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/api/v1/users/2/force-logout",
            data={"csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.id == 2).first()
            assert user is not None
            assert user.token_version == 2
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_admin_cannot_create_or_manage_other_users(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        main_module.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=2,
            username="editor",
            email="editor@example.com",
            role="admin",
            is_active=True,
            use_gravatar="auto",
        )
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)

        create_response = client.post(
            f"{admin_prefix}/api/v1/users",
            data={
                "username": "blockedadmin",
                "email": "blockedadmin@example.com",
                "password": "blocked123",
                "role": "admin",
                "csrf_token": csrf_token,
            },
        )
        assert create_response.status_code == 403

        role_response = client.post(
            f"{admin_prefix}/api/v1/users/1/role",
            data={"role": "super_admin", "csrf_token": csrf_token},
        )
        assert role_response.status_code == 403

        with session_factory() as db:
            missing = db.query(DbUser).filter(DbUser.username == "blockedadmin").first()
            assert missing is None
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_users_admin_actions_write_activity_summary(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)

        response = client.post(
            f"{admin_prefix}/api/v1/users/2/status",
            data={"is_active": "false", "csrf_token": csrf_token},
        )
        assert response.status_code == 200

        with session_factory() as db:
            activity_map = admin_security.get_admin_user_activity_map(db, user_ids=[2])
            payload = activity_map.get(2)
            assert payload is not None
            assert payload["event"] == "status_updated"
            assert payload["label"] == "状态已更新"
            assert payload["detail_text"] == "已停用"
            assert payload["actor_username"] == "admin"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_force_logout_invalidates_existing_token(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        with session_factory() as db:
            editor = db.query(DbUser).filter(DbUser.id == 2).first()
            assert editor is not None
            token = create_access_token(
                data={
                    "sub": str(editor.id),
                    "token_version": int(editor.token_version or 1),
                }
            )

        page = client.get(f"{admin_prefix}/users")
        csrf_token = _extract_csrf_token(page.text)
        force_response = client.post(
            f"{admin_prefix}/api/v1/users/2/force-logout",
            data={"csrf_token": csrf_token},
        )
        assert force_response.status_code == 200

        client.cookies.set("access_token", token)
        auth_status = client.get("/api/v1/auth/status")
        assert auth_status.status_code == 200
        assert auth_status.json()["logged_in"] is False

        main_module.app.dependency_overrides.pop(get_current_user, None)
        me_response = client.get("/users/me/")
        assert me_response.status_code == 401
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_admin_login_endpoint_sets_redirect_header(monkeypatch, tmp_path):
    client, _, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        main_module.app.dependency_overrides.pop(get_current_user, None)
        response = client.post(
            f"{admin_prefix}/auth",
            data={"username": "admin", "password": "adminpass123"},
        )
        assert response.status_code == 200
        assert response.headers.get("hx-redirect") == f"{admin_prefix}/dashboard"
        assert "access_token" in client.cookies
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_logout_clears_access_token_cookie(monkeypatch, tmp_path):
    client, _, engine = _build_admin_client(monkeypatch, tmp_path)
    try:
        client.cookies.set("access_token", "fake-token")
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        set_cookie = response.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()
