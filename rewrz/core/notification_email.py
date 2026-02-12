"""
邮件通知工具

提供项目内基础邮件发送能力（标准库 smtplib）。
若未配置 SMTP 环境变量，则静默返回 False。
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional


logger = logging.getLogger(__name__)


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _smtp_settings() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("SMTP_FROM", "").strip(),
        "use_tls": _get_bool_env("SMTP_USE_TLS", True),
        "use_ssl": _get_bool_env("SMTP_USE_SSL", False),
    }


def send_email(to_email: str, subject: str, body: str) -> bool:
    cfg = _smtp_settings()
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
) -> bool:
    subject = "[RewrZ] New Admin Login IP Detected"
    body = (
        "A new admin login IP was detected.\n\n"
        f"Username: {username}\n"
        f"IP: {ip_address}\n"
        f"User-Agent: {user_agent or 'unknown'}\n"
        f"Time: {login_time_text}\n"
    )
    return send_email(to_email, subject, body)


def send_new_comment_notification(
    to_email: str,
    post_title: str,
    author_name: str,
    author_email: str,
    comment_preview: str,
    review_url: str,
) -> bool:
    subject = "[RewrZ] New Comment Received"
    body = (
        "A new comment has been submitted.\n\n"
        f"Post: {post_title}\n"
        f"Author: {author_name} <{author_email}>\n"
        f"Comment: {comment_preview}\n\n"
        f"Review link: {review_url}\n"
    )
    return send_email(to_email, subject, body)
