import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core import admin_security
from rewrz.core.admin_security import (
    SECURITY_COMMENT_RATE_LIMIT_KEY,
    check_comment_rate_limit,
    count_login_attempts,
    get_ip_lock_state,
    is_new_ip_for_user,
    record_login_attempt,
    remember_user_ip,
)
from rewrz.core.database import Base
from rewrz.core.security import get_current_user, get_password_hash
from rewrz.crud import setting as crud_setting
from rewrz.models.setting import Setting
from rewrz.models.user import User as DbUser
from rewrz.schemas import SettingCreate, SettingUpdate


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
    db_path = tmp_path / Path(f"security-admin-{uuid4().hex}.db")
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

    from rewrz.core.database import get_db

    with testing_session_local() as db:
        _seed_admin_basics(db)

    main_module.app.dependency_overrides[get_db] = override_get_db
    main_module.app.dependency_overrides[get_current_user] = _login_user_override
    return TestClient(main_module.app), testing_session_local, engine


def test_record_login_attempt_writes_db_and_log(test_db, monkeypatch, tmp_path):
    Base.metadata.create_all(bind=test_db.get_bind())

    log_path = tmp_path / "admin_login_audit.log"
    monkeypatch.setattr(admin_security, "_AUDIT_LOG_PATH", Path(log_path))

    row = record_login_attempt(
        test_db,
        username="admin",
        ip_address="203.0.113.10",
        user_agent="pytest-agent",
        success=False,
        reason="bad_credentials",
    )

    assert row.id is not None
    assert log_path.exists()

    content = log_path.read_text(encoding="utf-8")
    assert "FAILED" in content
    assert "username=admin" in content
    assert "ip=203.0.113.10" in content


def test_ip_lock_state_unlocks_after_success(test_db):
    Base.metadata.create_all(bind=test_db.get_bind())

    ip = "198.51.100.9"
    for _ in range(2):
        record_login_attempt(
            test_db,
            username="admin",
            ip_address=ip,
            user_agent="pytest-agent",
            success=False,
            reason="bad_credentials",
        )

    blocked, remaining, failed_count = get_ip_lock_state(
        test_db, ip_address=ip, max_attempts=2, ban_minutes=15
    )
    assert blocked is True
    assert remaining > 0
    assert failed_count >= 2

    record_login_attempt(
        test_db,
        username="admin",
        ip_address=ip,
        user_agent="pytest-agent",
        success=True,
        reason="login_success",
    )
    blocked_after_success, _, failed_after_success = get_ip_lock_state(
        test_db, ip_address=ip, max_attempts=2, ban_minutes=15
    )
    assert blocked_after_success is False
    assert failed_after_success == 0


def test_comment_rate_limit_enforced(test_db):
    Base.metadata.create_all(bind=test_db.get_bind())
    admin_security._COMMENT_RATE_BUCKETS.clear()

    existing = crud_setting.get_setting(test_db, SECURITY_COMMENT_RATE_LIMIT_KEY)
    if existing is None:
        crud_setting.create_setting(
            test_db,
            SettingCreate(
                key=SECURITY_COMMENT_RATE_LIMIT_KEY,
                value={"value": 2},
                description="test-only",
            ),
        )
    else:
        crud_setting.update_setting(
            test_db,
            key=SECURITY_COMMENT_RATE_LIMIT_KEY,
            setting_update=SettingUpdate(value={"value": 2}),
        )

    ip = "192.0.2.55"
    allowed1, _ = check_comment_rate_limit(test_db, ip)
    allowed2, _ = check_comment_rate_limit(test_db, ip)
    allowed3, retry_after = check_comment_rate_limit(test_db, ip)

    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is False
    assert retry_after > 0


def test_new_ip_tracking(test_db):
    Base.metadata.create_all(bind=test_db.get_bind())

    username = "admin"
    ip = "203.0.113.88"

    assert is_new_ip_for_user(test_db, username, ip) is True
    remember_user_ip(test_db, username, ip)
    assert is_new_ip_for_user(test_db, username, ip) is False


def test_security_center_page_supports_pagination(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        with session_factory() as db:
            for index in range(25):
                record_login_attempt(
                    db,
                    username=f"admin{index}",
                    ip_address=f"203.0.113.{index}",
                    user_agent="pytest-agent",
                    success=index % 2 == 0,
                    reason="login_success" if index % 2 == 0 else "bad_credentials",
                )

        response = client.get(f"{admin_prefix}/security-center?page=2&page_size=20")
        assert response.status_code == 200
        assert "第 2 / 2 页" in response.text
        assert "共 25 条记录" in response.text
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_security_center_can_save_audit_cleanup_config(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    try:
        page = client.get(f"{admin_prefix}/security-center")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/security-center",
            data={
                "login_max_attempts": "4",
                "login_ban_minutes": "20",
                "new_ip_login_alert_enabled": "true",
                "comment_rate_limit_per_min": "40",
                "login_audit_auto_cleanup_enabled": "true",
                "login_audit_retention_days": "45",
                "csrf_token": csrf_token,
            },
        )
        assert response.status_code == 200
        assert "安全中心设置已保存" in response.text

        with session_factory() as db:
            config = admin_security.get_login_security_config(db)
            assert config["login_audit_auto_cleanup_enabled"] is True
            assert config["login_audit_retention_days"] == 45
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()


def test_security_center_can_clear_expired_audit_records(monkeypatch, tmp_path):
    client, session_factory, engine = _build_admin_client(monkeypatch, tmp_path)
    admin_prefix = main_module.settings.ADMIN_PATH.rstrip("/")
    log_path = tmp_path / "admin_login_audit.log"
    monkeypatch.setattr(admin_security, "_AUDIT_LOG_PATH", Path(log_path))
    try:
        with session_factory() as db:
            admin_security.save_security_config(
                db,
                login_max_attempts=3,
                login_ban_minutes=15,
                new_ip_login_alert_enabled=False,
                comment_rate_limit_per_min=30,
                login_audit_auto_cleanup_enabled=True,
                login_audit_retention_days=30,
            )
            old_row = record_login_attempt(
                db,
                username="old-admin",
                ip_address="203.0.113.20",
                user_agent="pytest-agent",
                success=False,
                reason="bad_credentials",
            )
            fresh_row = record_login_attempt(
                db,
                username="new-admin",
                ip_address="203.0.113.21",
                user_agent="pytest-agent",
                success=True,
                reason="login_success",
            )
            old_row.created_at = admin_security._to_naive(admin_security._now_utc()) - timedelta(days=45)
            fresh_row.created_at = admin_security._to_naive(admin_security._now_utc())
            db.commit()

        page = client.get(f"{admin_prefix}/security-center")
        csrf_token = _extract_csrf_token(page.text)
        response = client.post(
            f"{admin_prefix}/security-center/audit/cleanup",
            data={"clear_mode": "expired", "csrf_token": csrf_token},
        )
        assert response.status_code == 200
        assert "已清理超过 30 天的登录审计" in response.text

        with session_factory() as db:
            assert count_login_attempts(db) == 1
    finally:
        main_module.app.dependency_overrides.clear()
        engine.dispose()
