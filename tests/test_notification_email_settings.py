from rewrz.core.notification_email import _smtp_settings, is_email_delivery_configured
from rewrz.models.setting import Setting


def test_smtp_settings_prefer_database_values(test_db, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "env.smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "env-user")
    monkeypatch.setenv("SMTP_PASSWORD", "env-pass")
    monkeypatch.setenv("SMTP_FROM", "env-from@example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "true")

    for key, value in {
        "smtp_host": "db.smtp.example.com",
        "smtp_port": 465,
        "smtp_username": "db-user",
        "smtp_password": "db-pass",
        "smtp_from_email": "db-from@example.com",
        "smtp_use_tls": True,
        "smtp_use_ssl": False,
    }.items():
        existing = test_db.query(Setting).filter(Setting.key == key).first()
        if existing is None:
            test_db.add(Setting(key=key, value={"value": value}, description=f"测试设置：{key}"))
            continue
        existing.value = {"value": value}
    test_db.commit()

    cfg = _smtp_settings(test_db)
    assert cfg["host"] == "db.smtp.example.com"
    assert cfg["port"] == 465
    assert cfg["username"] == "db-user"
    assert cfg["password"] == "db-pass"
    assert cfg["from_email"] == "db-from@example.com"
    assert cfg["use_tls"] is True
    assert cfg["use_ssl"] is False
    assert is_email_delivery_configured(test_db) is True


def test_smtp_settings_fall_back_to_environment_when_database_missing(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "env.smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "env-user")
    monkeypatch.setenv("SMTP_PASSWORD", "env-pass")
    monkeypatch.setenv("SMTP_FROM", "env-from@example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "true")

    cfg = _smtp_settings()
    assert cfg["host"] == "env.smtp.example.com"
    assert cfg["port"] == 2525
    assert cfg["username"] == "env-user"
    assert cfg["password"] == "env-pass"
    assert cfg["from_email"] == "env-from@example.com"
    assert cfg["use_tls"] is False
    assert cfg["use_ssl"] is True
