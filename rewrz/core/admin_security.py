"""
后台安全核心服务

覆盖以下能力：
1. 登录失败次数限制与 IP 临时封禁
2. 登录审计（数据库 + 文件日志）
3. 新 IP 登录识别
4. 评论提交接口速率限制（按 IP）
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..crud import setting as crud_setting
from ..models.login_attempt import LoginAttempt
from ..schemas import SettingCreate, SettingUpdate


SECURITY_LOGIN_MAX_ATTEMPTS_KEY = "security_login_max_attempts"
SECURITY_LOGIN_BAN_MINUTES_KEY = "security_login_ban_minutes"
SECURITY_NEW_IP_ALERT_ENABLED_KEY = "security_new_ip_login_alert_enabled"
SECURITY_KNOWN_LOGIN_IPS_KEY = "security_known_login_ips"
SECURITY_COMMENT_RATE_LIMIT_KEY = "security_comment_rate_limit_per_min"

DEFAULT_LOGIN_MAX_ATTEMPTS = 3
DEFAULT_LOGIN_BAN_MINUTES = 15
DEFAULT_NEW_IP_ALERT_ENABLED = False
DEFAULT_COMMENT_RATE_LIMIT_PER_MIN = 30

_AUDIT_LOG_PATH = Path("data/logs/admin_login_audit.log")

_COMMENT_RATE_BUCKETS: Dict[str, Deque[float]] = defaultdict(deque)
_COMMENT_RATE_LOCK = threading.Lock()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _get_setting_value(db: Session, key: str, default):
    setting = crud_setting.get_setting(db, key)
    if not setting or not setting.value:
        return default
    return setting.value.get("value", default)


def _upsert_setting(db: Session, key: str, value, description: str) -> None:
    payload = {"value": value}
    existing = crud_setting.get_setting(db, key)
    if existing:
        crud_setting.update_setting(db, key=key, setting_update=SettingUpdate(value=payload))
        return
    crud_setting.create_setting(
        db,
        SettingCreate(
            key=key,
            value=payload,
            description=description,
        ),
    )


def get_login_security_config(db: Session) -> dict:
    return {
        "login_max_attempts": int(
            _get_setting_value(db, SECURITY_LOGIN_MAX_ATTEMPTS_KEY, DEFAULT_LOGIN_MAX_ATTEMPTS)
        ),
        "login_ban_minutes": int(
            _get_setting_value(db, SECURITY_LOGIN_BAN_MINUTES_KEY, DEFAULT_LOGIN_BAN_MINUTES)
        ),
        "new_ip_login_alert_enabled": bool(
            _get_setting_value(db, SECURITY_NEW_IP_ALERT_ENABLED_KEY, DEFAULT_NEW_IP_ALERT_ENABLED)
        ),
        "comment_rate_limit_per_min": int(
            _get_setting_value(
                db, SECURITY_COMMENT_RATE_LIMIT_KEY, DEFAULT_COMMENT_RATE_LIMIT_PER_MIN
            )
        ),
    }


def save_security_config(
    db: Session,
    *,
    login_max_attempts: int,
    login_ban_minutes: int,
    new_ip_login_alert_enabled: bool,
    comment_rate_limit_per_min: int,
) -> None:
    _upsert_setting(
        db,
        SECURITY_LOGIN_MAX_ATTEMPTS_KEY,
        int(login_max_attempts),
        "后台登录允许的失败次数",
    )
    _upsert_setting(
        db,
        SECURITY_LOGIN_BAN_MINUTES_KEY,
        int(login_ban_minutes),
        "后台登录失败后IP封禁时长（分钟）",
    )
    _upsert_setting(
        db,
        SECURITY_NEW_IP_ALERT_ENABLED_KEY,
        bool(new_ip_login_alert_enabled),
        "是否启用后台新IP登录邮件告警",
    )
    _upsert_setting(
        db,
        SECURITY_COMMENT_RATE_LIMIT_KEY,
        int(comment_rate_limit_per_min),
        "评论提交API每分钟请求上限（按IP）",
    )


def get_client_ip(request) -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _write_audit_log(
    *,
    username: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    reason: str,
) -> None:
    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "SUCCESS" if success else "FAILED"
    line = (
        f"{ts}\t{status}\tusername={username}\tip={ip_address}\t"
        f"user_agent={user_agent or '-'}\treason={reason or '-'}\n"
    )
    with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(line)


def record_login_attempt(
    db: Session,
    *,
    username: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    reason: str,
) -> LoginAttempt:
    row = LoginAttempt(
        username=username or "",
        ip_address=ip_address or "unknown",
        user_agent=user_agent or "",
        success=bool(success),
        reason=reason or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    _write_audit_log(
        username=username or "",
        ip_address=ip_address or "unknown",
        user_agent=user_agent or "",
        success=bool(success),
        reason=reason or "",
    )
    return row


def get_recent_login_attempts(db: Session, limit: int = 50) -> List[LoginAttempt]:
    return list(
        db.execute(
            select(LoginAttempt).order_by(LoginAttempt.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )


def get_ip_lock_state(
    db: Session,
    *,
    ip_address: str,
    max_attempts: int,
    ban_minutes: int,
) -> Tuple[bool, int, int]:
    now = _to_naive(_now_utc())
    window_start = now - timedelta(minutes=ban_minutes)

    last_success_time = db.execute(
        select(func.max(LoginAttempt.created_at)).where(
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.success.is_(True),
        )
    ).scalar_one_or_none()
    if last_success_time is not None:
        last_success_time = _to_naive(last_success_time)

    cutoff = max(window_start, last_success_time) if last_success_time else window_start

    failed_count = int(
        db.execute(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.ip_address == ip_address,
                LoginAttempt.success.is_(False),
                LoginAttempt.created_at >= cutoff,
            )
        ).scalar_one()
    )

    last_failed_time = db.execute(
        select(func.max(LoginAttempt.created_at)).where(
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    ).scalar_one_or_none()
    if last_failed_time is None:
        return False, 0, failed_count

    last_failed_time = _to_naive(last_failed_time)
    unlock_at = last_failed_time + timedelta(minutes=ban_minutes)
    if failed_count >= max_attempts and now < unlock_at:
        remaining_seconds = int((unlock_at - now).total_seconds())
        return True, max(remaining_seconds, 1), failed_count
    return False, 0, failed_count


def _load_known_ips(db: Session) -> dict:
    raw = _get_setting_value(db, SECURITY_KNOWN_LOGIN_IPS_KEY, {})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def is_new_ip_for_user(db: Session, username: str, ip_address: str) -> bool:
    known = _load_known_ips(db)
    user_known = known.get(username, [])
    return ip_address not in user_known


def remember_user_ip(db: Session, username: str, ip_address: str) -> None:
    known = _load_known_ips(db)
    user_known = list(known.get(username, []))
    if ip_address in user_known:
        return
    user_known.append(ip_address)
    known[username] = user_known[-20:]  # 保留最近20个历史IP
    _upsert_setting(
        db,
        SECURITY_KNOWN_LOGIN_IPS_KEY,
        known,
        "后台登录用户名与已知IP映射",
    )


def get_admin_email(db: Session) -> Optional[str]:
    setting = crud_setting.get_setting(db, "admin_email")
    if not setting or not setting.value:
        return None
    value = setting.value.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def check_comment_rate_limit(db: Session, ip_address: str) -> Tuple[bool, int]:
    limit = int(
        _get_setting_value(db, SECURITY_COMMENT_RATE_LIMIT_KEY, DEFAULT_COMMENT_RATE_LIMIT_PER_MIN)
    )
    if limit <= 0:
        return True, 0

    now_ts = time.time()
    with _COMMENT_RATE_LOCK:
        bucket = _COMMENT_RATE_BUCKETS[ip_address]
        while bucket and now_ts - bucket[0] >= 60:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = max(int(60 - (now_ts - bucket[0])), 1)
            return False, retry_after

        bucket.append(now_ts)
        return True, 0
