import re
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core.database import Base, get_db
from rewrz.core.security import create_access_token, get_password_hash, verify_password
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


def _seed_password_reset_basics(db) -> None:
    existing_admin = db.query(DbUser).filter(DbUser.id == 1).first()
    if existing_admin is None:
        db.add(
            DbUser(
                id=1,
                username="reset_admin",
                hashed_password=get_password_hash("OldPass123!"),
                email="reset_admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
                display_name="重置管理员",
                token_version=1,
            )
        )

    existing_keys = {item.key for item in db.query(Setting).all()}
    for key, value in {
        "site_title": {"value": "RewrZ Test"},
        "admin_email": {"value": "admin@example.com"},
        "site_url": {"value": "http://testserver"},
    }.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value, description=f"测试设置：{key}"))

    db.commit()


def _extract_csrf_token(response_text: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def _extract_reset_url(debug_log_path: Path) -> str:
    content = debug_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert content
    last_line = content[-1]
    match = re.search(r"reset_url=(https?://\S+|http://\S+)", last_line)
    assert match is not None
    return match.group(1)


def _build_client(monkeypatch, tmp_path) -> tuple[TestClient, sessionmaker, object]:
    _set_installation_complete(monkeypatch, True)
    _ensure_admin_routes_registered()
    for env_name in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_USE_TLS",
        "SMTP_USE_SSL",
    ):
        monkeypatch.delenv(env_name, raising=False)
    db_path = tmp_path / Path(f"auth-reset-{uuid4().hex}.db")
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
        _seed_password_reset_basics(db)

    main_module.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main_module.app), testing_session_local, engine


def test_login_page_exposes_forgot_password_link(monkeypatch, tmp_path):
    client, _, engine = _build_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.get(f"{admin_prefix}/login")
        assert response.status_code == 200
        assert "忘记密码" in response.text
        assert f'{admin_prefix}/forgot-password' in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_forgot_password_request_masks_unknown_user(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    debug_log_path = tmp_path / "password_reset_debug.log"
    monkeypatch.setenv("PASSWORD_RESET_DEBUG_LOG_PATH", str(debug_log_path))
    try:
        page = client.get(f"{admin_prefix}/forgot-password")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/forgot-password",
            data={"identifier": "missing_user", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert "请求已受理，请检查邮箱或调试投递记录。" in response.text
        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.username == "reset_admin").first()
            assert user is not None
            assert user.password_reset_token_hash is None
        assert debug_log_path.exists() is False
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_forgot_password_request_writes_debug_delivery_and_reset_succeeds(monkeypatch, tmp_path):
    client, session_factory, engine = _build_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    debug_log_path = tmp_path / "password_reset_debug.log"
    monkeypatch.setenv("PASSWORD_RESET_DEBUG_LOG_PATH", str(debug_log_path))
    try:
        login_response = client.post(
            f"{admin_prefix}/auth",
            data={"username": "reset_admin", "password": "OldPass123!"},
        )
        assert login_response.status_code == 200
        old_token = client.cookies.get("access_token")
        assert old_token
        client.cookies.clear()

        page = client.get(f"{admin_prefix}/forgot-password")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/forgot-password",
            data={"identifier": "reset_admin@example.com", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert "请求已受理，请检查邮箱或调试投递记录。" in response.text
        assert debug_log_path.exists() is True

        reset_url = _extract_reset_url(debug_log_path)
        reset_page = client.get(reset_url)
        assert reset_page.status_code == 200
        assert "设置新密码" in reset_page.text
        reset_csrf_token = _extract_csrf_token(reset_page.text)
        token_match = re.search(r'name="token"\s+value="([^"]+)"', reset_page.text)
        assert token_match is not None
        raw_token = token_match.group(1)

        submit_response = client.post(
            f"{admin_prefix}/reset-password",
            data={
                "token": raw_token,
                "password": "NewPass123!",
                "password_confirm": "NewPass123!",
                "csrf_token": reset_csrf_token,
            },
            follow_redirects=False,
        )
        assert submit_response.status_code == 303
        assert submit_response.headers["location"] == f"{admin_prefix}/login?reset=success"

        with session_factory() as db:
            user = db.query(DbUser).filter(DbUser.username == "reset_admin").first()
            assert user is not None
            assert verify_password("NewPass123!", user.hashed_password)
            assert user.token_version == 2
            assert user.password_reset_token_hash is None
            assert user.password_reset_sent_at is None
            assert user.password_reset_expires_at is None

        client.cookies.set("access_token", old_token)
        auth_status = client.get("/api/v1/auth/status")
        assert auth_status.status_code == 200
        assert auth_status.json()["logged_in"] is False

        client.cookies.clear()
        new_login = client.post(
            f"{admin_prefix}/auth",
            data={"username": "reset_admin", "password": "NewPass123!"},
        )
        assert new_login.status_code == 200
        assert new_login.headers.get("hx-redirect") == f"{admin_prefix}/dashboard"
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_reset_password_rejects_invalid_token(monkeypatch, tmp_path):
    client, _, engine = _build_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.get(f"{admin_prefix}/reset-password?token=invalid-token")
        assert response.status_code == 400
        assert "重置链接无效或已过期" in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()
