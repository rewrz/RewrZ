from pathlib import Path

from rewrz.core import admin_security
from rewrz.core.admin_security import (
    SECURITY_COMMENT_RATE_LIMIT_KEY,
    check_comment_rate_limit,
    get_ip_lock_state,
    is_new_ip_for_user,
    record_login_attempt,
    remember_user_ip,
)
from rewrz.core.database import Base
from rewrz.crud import setting as crud_setting
from rewrz.schemas import SettingCreate, SettingUpdate


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
