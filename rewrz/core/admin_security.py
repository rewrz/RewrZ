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
SECURITY_LOGIN_AUDIT_AUTO_CLEANUP_ENABLED_KEY = "security_login_audit_auto_cleanup_enabled"
SECURITY_LOGIN_AUDIT_RETENTION_DAYS_KEY = "security_login_audit_retention_days"
SECURITY_LOGIN_AUDIT_LAST_CLEANED_AT_KEY = "security_login_audit_last_cleaned_at"
ADMIN_USER_ACTIVITY_SUMMARY_KEY = "admin_user_activity_summary"

DEFAULT_LOGIN_MAX_ATTEMPTS = 3
DEFAULT_LOGIN_BAN_MINUTES = 15
DEFAULT_NEW_IP_ALERT_ENABLED = False
DEFAULT_COMMENT_RATE_LIMIT_PER_MIN = 30
DEFAULT_LOGIN_AUDIT_AUTO_CLEANUP_ENABLED = False
DEFAULT_LOGIN_AUDIT_RETENTION_DAYS = 30
ADMIN_ROLE_LABELS = {
    "admin": "普通管理员",
    "super_admin": "超级管理员",
}

_AUDIT_LOG_PATH = Path("data/logs/admin_login_audit.log")
_ADMIN_ACTION_AUDIT_LOG_PATH = Path("data/logs/admin_action_audit.log")

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
        "login_audit_auto_cleanup_enabled": bool(
            _get_setting_value(
                db,
                SECURITY_LOGIN_AUDIT_AUTO_CLEANUP_ENABLED_KEY,
                DEFAULT_LOGIN_AUDIT_AUTO_CLEANUP_ENABLED,
            )
        ),
        "login_audit_retention_days": int(
            _get_setting_value(
                db,
                SECURITY_LOGIN_AUDIT_RETENTION_DAYS_KEY,
                DEFAULT_LOGIN_AUDIT_RETENTION_DAYS,
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
    login_audit_auto_cleanup_enabled: bool,
    login_audit_retention_days: int,
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
    _upsert_setting(
        db,
        SECURITY_LOGIN_AUDIT_AUTO_CLEANUP_ENABLED_KEY,
        bool(login_audit_auto_cleanup_enabled),
        "是否启用登录审计自动清理",
    )
    _upsert_setting(
        db,
        SECURITY_LOGIN_AUDIT_RETENTION_DAYS_KEY,
        int(login_audit_retention_days),
        "登录审计自动清理保留天数",
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


def _write_admin_action_log(record: dict) -> None:
    _ADMIN_ACTION_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _ADMIN_ACTION_AUDIT_LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def _load_admin_user_activity_summary(db: Session) -> dict:
    raw = _get_setting_value(db, ADMIN_USER_ACTIVITY_SUMMARY_KEY, {})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def get_admin_user_activity_map(
    db: Session,
    user_ids: Optional[List[int]] = None,
) -> Dict[int, dict]:
    raw_summary = _load_admin_user_activity_summary(db)
    normalized: Dict[int, dict] = {}
    allowed_ids = {int(user_id) for user_id in (user_ids or [])}

    for raw_user_id, raw_payload in raw_summary.items():
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        if allowed_ids and user_id not in allowed_ids:
            continue
        if not isinstance(raw_payload, dict):
            continue
        normalized[user_id] = raw_payload
    return normalized


def record_admin_user_action(
    db: Session,
    *,
    event: str,
    actor_user_id: int,
    actor_username: str,
    target_user_id: int,
    target_username: str,
    ip_address: str,
    detail: Optional[dict] = None,
) -> None:
    normalized_event = str(event or "").strip().lower() or "unknown"
    now_utc = _now_utc()
    detail_payload = detail if isinstance(detail, dict) else {}
    detail_role = ADMIN_ROLE_LABELS.get(
        str(detail_payload.get("role", "") or "").strip().lower(),
        str(detail_payload.get("role", "-") or "-"),
    )

    event_labels = {
        "status_updated": "状态已更新",
        "role_updated": "角色已更新",
        "password_reset": "密码已重置",
        "force_logout": "已强制退出",
        "created": "已创建用户",
    }
    detail_lines = {
        "status_updated": (
            "已启用"
            if bool(detail_payload.get("is_active"))
            else "已停用"
        ),
        "role_updated": f"角色切换为 {detail_role}",
        "password_reset": "管理员已重置密码",
        "force_logout": "现有登录态已失效",
        "created": f"新建角色 {detail_role}",
    }

    record = {
        "event": normalized_event,
        "timestamp": now_utc.isoformat(),
        "actor_user_id": int(actor_user_id),
        "actor_username": str(actor_username or "").strip(),
        "target_user_id": int(target_user_id),
        "target_username": str(target_username or "").strip(),
        "ip_address": str(ip_address or "unknown").strip() or "unknown",
        "detail": detail_payload,
    }
    _write_admin_action_log(record)

    summary = _load_admin_user_activity_summary(db)
    summary[str(int(target_user_id))] = {
        "event": normalized_event,
        "label": event_labels.get(normalized_event, "后台管理操作"),
        "detail_text": detail_lines.get(normalized_event, "管理员执行了操作"),
        "timestamp": now_utc.isoformat(),
        "actor_username": str(actor_username or "").strip(),
        "ip_address": str(ip_address or "unknown").strip() or "unknown",
    }
    _upsert_setting(
        db,
        ADMIN_USER_ACTIVITY_SUMMARY_KEY,
        summary,
        "后台用户管理最近活动摘要",
    )


def get_recent_login_attempts(db: Session, limit: int = 50) -> List[LoginAttempt]:
    return list(
        db.execute(
            select(LoginAttempt).order_by(LoginAttempt.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )


def count_login_attempts(db: Session) -> int:
    return int(db.execute(select(func.count(LoginAttempt.id))).scalar_one() or 0)


def get_login_attempts_paginated(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
) -> List[LoginAttempt]:
    return list(
        db.execute(
            select(LoginAttempt)
            .order_by(LoginAttempt.created_at.desc())
            .offset(max(0, int(skip)))
            .limit(max(1, int(limit)))
        )
        .scalars()
        .all()
    )


def clear_login_attempts(
    db: Session,
    *,
    older_than_days: int | None = None,
) -> int:
    stmt = select(LoginAttempt)
    if older_than_days is not None:
        cutoff = _to_naive(_now_utc()) - timedelta(days=max(1, int(older_than_days)))
        stmt = stmt.where(LoginAttempt.created_at < cutoff)

    rows = db.execute(stmt).scalars().all()
    deleted_count = len(rows)
    if deleted_count == 0:
        return 0

    for row in rows:
        db.delete(row)
    db.commit()
    return deleted_count


def truncate_login_audit_log() -> None:
    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _AUDIT_LOG_PATH.write_text("", encoding="utf-8")


def prune_login_audit_log(*, older_than_days: int) -> int:
    retention_days = max(1, int(older_than_days))
    if not _AUDIT_LOG_PATH.exists():
        return 0

    cutoff = _to_naive(_now_utc()) - timedelta(days=retention_days)
    kept_lines: List[str] = []
    removed_count = 0

    for raw_line in _AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").rstrip("\n")
        if not line:
            continue
        timestamp_text = line.split("\t", 1)[0].strip()
        try:
            parsed_time = datetime.strptime(timestamp_text, "%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            kept_lines.append(line)
            continue
        if parsed_time < cutoff:
            removed_count += 1
            continue
        kept_lines.append(line)

    output = "\n".join(kept_lines)
    if output:
        output += "\n"
    _AUDIT_LOG_PATH.write_text(output, encoding="utf-8")
    return removed_count


def mark_login_audit_cleanup_run(db: Session, *, cleaned_at: datetime | None = None) -> None:
    timestamp = (cleaned_at or _now_utc()).astimezone(timezone.utc).isoformat()
    _upsert_setting(
        db,
        SECURITY_LOGIN_AUDIT_LAST_CLEANED_AT_KEY,
        timestamp,
        "登录审计最近一次清理时间",
    )


def _parse_iso_datetime(raw_value: object) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_run_login_audit_auto_cleanup(db: Session, *, now: datetime | None = None) -> bool:
    config = get_login_security_config(db)
    if not bool(config.get("login_audit_auto_cleanup_enabled")):
        return False

    current = (now or _now_utc()).astimezone(timezone.utc)
    last_cleaned_at = _parse_iso_datetime(
        _get_setting_value(db, SECURITY_LOGIN_AUDIT_LAST_CLEANED_AT_KEY, "")
    )
    if last_cleaned_at is None:
        return True
    return last_cleaned_at.date() < current.date()


def run_login_audit_auto_cleanup(db: Session) -> int:
    config = get_login_security_config(db)
    retention_days = max(1, int(config.get("login_audit_retention_days", DEFAULT_LOGIN_AUDIT_RETENTION_DAYS) or DEFAULT_LOGIN_AUDIT_RETENTION_DAYS))
    deleted_count = clear_login_attempts(db, older_than_days=retention_days)
    prune_login_audit_log(older_than_days=retention_days)
    mark_login_audit_cleanup_run(db)
    return deleted_count


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
