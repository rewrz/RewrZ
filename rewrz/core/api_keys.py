from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..crud import api_key as crud_api_key
from ..core.database import get_db
from ..core.security import get_client_ip
from ..schemas.api_key import API_KEY_ACCESS_LEVELS


API_KEY_PREFIX = "rwz"
API_KEY_AUDIT_LOG_PATH = Path("data/logs/api_key_audit.log")
EXTERNAL_API_LEVELS = {
    "read_only": {
        "posts.read",
        "pages.read",
        "categories.read",
        "tags.read",
    },
    "writer": {
        "posts.read",
        "pages.read",
        "categories.read",
        "tags.read",
        "posts.write",
        "pages.write",
        "media.write",
    },
    "publisher": {
        "posts.read",
        "pages.read",
        "categories.read",
        "tags.read",
        "posts.write",
        "pages.write",
        "media.write",
        "posts.publish",
        "pages.publish",
    },
    "manager": {
        "posts.read",
        "pages.read",
        "categories.read",
        "tags.read",
        "posts.write",
        "pages.write",
        "media.write",
        "posts.publish",
        "pages.publish",
        "posts.delete",
        "pages.delete",
    },
}

bearer_scheme = HTTPBearer(auto_error=False)


def _ensure_log_parent() -> None:
    API_KEY_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def write_api_key_audit_log(event: str, payload: dict) -> None:
    _ensure_log_parent()
    record = {
        "event": str(event or "").strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with API_KEY_AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_api_key_plaintext() -> tuple[str, str]:
    prefix = f"{API_KEY_PREFIX}_{secrets.token_hex(4)}"
    secret = secrets.token_urlsafe(24)
    return prefix, f"{prefix}.{secret}"


def hash_api_key_secret(plain_token: str) -> str:
    return hashlib.sha256(str(plain_token or "").encode("utf-8")).hexdigest()


def verify_api_key_secret(plain_token: str, secret_hash: str) -> bool:
    candidate = hash_api_key_secret(plain_token)
    return secrets.compare_digest(candidate, str(secret_hash or ""))


def get_access_level_permissions(access_level: str) -> set[str]:
    normalized = str(access_level or "").strip().lower()
    if normalized not in API_KEY_ACCESS_LEVELS:
        normalized = "read_only"
    return set(EXTERNAL_API_LEVELS.get(normalized, set()))


def ensure_api_key_permission(api_key_obj, permission: str) -> None:
    normalized_permission = str(permission or "").strip().lower()
    if not normalized_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="外部 API 权限不足")
    granted = get_access_level_permissions(getattr(api_key_obj, "access_level", "read_only"))
    if normalized_permission not in granted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="外部 API 权限不足")


async def get_current_external_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None or str(credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key")

    plain_token = str(credentials.credentials or "").strip()
    if "." not in plain_token:
        write_api_key_audit_log(
            "auth_failed",
            {"reason": "malformed_token", "ip": get_client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")

    key_prefix, _ = plain_token.split(".", 1)
    db_api_key = crud_api_key.get_api_key_by_prefix(db, key_prefix)
    if db_api_key is None:
        write_api_key_audit_log(
            "auth_failed",
            {"reason": "key_not_found", "key_prefix": key_prefix, "ip": get_client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")

    if str(getattr(db_api_key, "status", "") or "").strip().lower() != "active":
        write_api_key_audit_log(
            "auth_failed",
            {"reason": "key_disabled", "key_prefix": key_prefix, "ip": get_client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 已停用")

    expires_at = getattr(db_api_key, "expires_at", None)
    if expires_at is not None and expires_at < datetime.now():
        write_api_key_audit_log(
            "auth_failed",
            {"reason": "key_expired", "key_prefix": key_prefix, "ip": get_client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 已过期")

    if not verify_api_key_secret(plain_token, getattr(db_api_key, "secret_hash", "")):
        write_api_key_audit_log(
            "auth_failed",
            {"reason": "secret_mismatch", "key_prefix": key_prefix, "ip": get_client_ip(request)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")

    used_ip = get_client_ip(request)
    crud_api_key.touch_api_key_usage(db, db_api_key.id, used_ip=used_ip)
    refreshed_api_key = crud_api_key.get_api_key(db, db_api_key.id) or db_api_key
    write_api_key_audit_log(
        "auth_succeeded",
        {
            "key_prefix": refreshed_api_key.key_prefix,
            "access_level": refreshed_api_key.access_level,
            "ip": used_ip,
            "path": str(request.url.path or ""),
        },
    )
    return refreshed_api_key
