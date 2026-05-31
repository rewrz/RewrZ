"""
邮件通知工具

提供项目内基础邮件发送能力（标准库 smtplib）。
优先读取后台常规设置中的 SMTP 配置；未配置时回退到环境变量。
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..crud import setting as crud_setting


logger = logging.getLogger(__name__)
_SMTP_SETTING_KEYS = [
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_from_email",
    "smtp_use_tls",
    "smtp_use_ssl",
]


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _smtp_settings_from_db(db: Session) -> dict:
    values = crud_setting.get_settings_by_keys(db, _SMTP_SETTING_KEYS)
    try:
        port = int(values.get("smtp_port", 587))
    except (TypeError, ValueError):
        port = 587

    return {
        "host": str(values.get("smtp_host", "") or "").strip(),
        "port": port,
        "username": str(values.get("smtp_username", "") or "").strip(),
        "password": str(values.get("smtp_password", "") or "").strip(),
        "from_email": str(values.get("smtp_from_email", "") or "").strip(),
        "use_tls": bool(values.get("smtp_use_tls", True)),
        "use_ssl": bool(values.get("smtp_use_ssl", False)),
    }


def _smtp_settings_from_env() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("SMTP_FROM", "").strip(),
        "use_tls": _get_bool_env("SMTP_USE_TLS", True),
        "use_ssl": _get_bool_env("SMTP_USE_SSL", False),
    }


def _smtp_settings(db: Session | None = None) -> dict:
    if db is not None:
        db_cfg = _smtp_settings_from_db(db)
        if db_cfg["host"]:
            return db_cfg
    return _smtp_settings_from_env()


def is_email_delivery_configured(db: Session | None = None) -> bool:
    """检查当前是否已配置基础邮件投递能力。"""
    cfg = _smtp_settings(db)
    return bool(cfg["host"])


def send_email(to_email: str, subject: str, body: str, *, db: Session | None = None) -> bool:
    cfg = _smtp_settings(db)
    if not cfg["host"] or not to_email:
        return False

    from_email = cfg["from_email"] or cfg["username"] or "no-reply@localhost"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if cfg["use_ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=10) as server:
                if cfg["username"] and cfg["password"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
                if cfg["use_tls"]:
                    server.starttls()
                if cfg["username"] and cfg["password"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("Email send failed: %s", exc)
        return False


def send_new_ip_login_alert(
    to_email: str,
    username: str,
    ip_address: str,
    user_agent: Optional[str],
    login_time_text: str,
    *,
    db: Session | None = None,
) -> bool:
    subject = "[RewrZ] New Admin Login IP Detected"
    body = (
        "A new admin login IP was detected.\n\n"
        f"Username: {username}\n"
        f"IP: {ip_address}\n"
        f"User-Agent: {user_agent or 'unknown'}\n"
        f"Time: {login_time_text}\n"
    )
    return send_email(to_email, subject, body, db=db)


def send_password_reset_email(
    to_email: str,
    *,
    username: str,
    reset_url: str,
    expire_minutes: int,
    db: Session | None = None,
) -> bool:
    subject = "[RewrZ] 后台账户密码重置"
    body = (
        "收到后台账户密码重置申请。\n\n"
        f"用户名：{username}\n"
        f"重置链接：{reset_url}\n"
        f"链接有效期：{int(expire_minutes)} 分钟\n\n"
        "如果这不是您本人操作，请忽略本邮件。链接仅可使用一次。\n"
    )
    return send_email(to_email, subject, body, db=db)


def write_password_reset_debug_delivery(
    *,
    username: str,
    email: str,
    reset_url: str,
    expires_at: datetime,
) -> str:
    """在未配置 SMTP 的开发环境中写入调试投递记录。"""
    log_path = Path(os.getenv("PASSWORD_RESET_DEBUG_LOG_PATH", "data/logs/password_reset_debug.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    expires_text = expires_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    line = (
        f"[{datetime.now().astimezone().isoformat()}] "
        f"username={username} email={email} expires_at={expires_text} reset_url={reset_url}\n"
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return str(log_path)


def send_new_comment_notification(
    to_email: str,
    post_title: str,
    author_name: str,
    author_email: str,
    comment_preview: str,
    review_url: str,
    *,
    db: Session | None = None,
) -> bool:
    subject = "[RewrZ] New Comment Received"
    body = (
        "A new comment has been submitted.\n\n"
        f"Post: {post_title}\n"
        f"Author: {author_name} <{author_email}>\n"
        f"Comment: {comment_preview}\n\n"
        f"Review link: {review_url}\n"
    )
    return send_email(to_email, subject, body, db=db)
