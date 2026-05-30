from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.api_keys import (
    build_api_key_plaintext,
    hash_api_key_secret,
    write_api_key_audit_log,
)
from ..core.security import ensure_admin_user, get_client_ip, get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import api_key as crud_api_key
from ..schemas import ApiKeyCreate, ApiKeyRotateRequest, ApiKeyStatusUpdate, ApiKeyUpdate, User


router = APIRouter()
templates = get_templates()


async def admin_api_keys_page(request: Request, db: Session, current_user: User):
    ensure_admin_user(current_user)
    api_keys = crud_api_key.get_api_keys(db)
    return templates.TemplateResponse(
        "admin/api_keys.html",
        {
            "request": request,
            "user": current_user,
            "api_keys": api_keys,
            "access_levels": ["read_only", "writer", "publisher", "manager"],
        },
    )


@router.get("/api/v1/admin/api-keys")
async def get_api_keys_public_guard():
    raise HTTPException(status_code=404, detail="Not found")


async def create_api_key_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    name: str,
    access_level: str,
    notes: Optional[str],
    expires_at_text: Optional[str],
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    expires_at = None
    raw_expires_at = str(expires_at_text or "").strip()
    if raw_expires_at:
        try:
            from datetime import datetime

            expires_at = datetime.fromisoformat(raw_expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="过期时间格式不正确") from exc

    payload = ApiKeyCreate(
        name=name,
        access_level=access_level,
        notes=notes,
        expires_at=expires_at,
    )
    key_prefix, plain_token = build_api_key_plaintext()
    db_api_key = crud_api_key.create_api_key(
        db,
        payload,
        key_prefix=key_prefix,
        secret_hash=hash_api_key_secret(plain_token),
        created_by_user_id=current_user.id,
    )
    write_api_key_audit_log(
        "created",
        {
            "key_prefix": db_api_key.key_prefix,
            "access_level": db_api_key.access_level,
            "operator_user_id": current_user.id,
            "ip": get_client_ip(request),
        },
    )
    return JSONResponse(
        {
            "success": True,
            "message": "API Key 已创建，请立即保存明文密钥",
            "api_key": {
                "id": db_api_key.id,
                "name": db_api_key.name,
                "key_prefix": db_api_key.key_prefix,
                "access_level": db_api_key.access_level,
                "status": db_api_key.status,
            },
            "plain_token": plain_token,
        }
    )


async def update_api_key_status_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    api_key_id: int,
    status_value: str,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    payload = ApiKeyStatusUpdate(status=status_value)
    db_api_key = crud_api_key.update_api_key_status(db, api_key_id, payload.status)
    if db_api_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    write_api_key_audit_log(
        "status_changed",
        {
            "key_prefix": db_api_key.key_prefix,
            "status": db_api_key.status,
            "operator_user_id": current_user.id,
            "ip": get_client_ip(request),
        },
    )
    return {"success": True, "message": "API Key 状态已更新"}


async def rotate_api_key_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    api_key_id: int,
    expires_at_text: Optional[str],
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    expires_at = None
    raw_expires_at = str(expires_at_text or "").strip()
    if raw_expires_at:
        try:
            from datetime import datetime

            expires_at = datetime.fromisoformat(raw_expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="过期时间格式不正确") from exc

    ApiKeyRotateRequest(expires_at=expires_at)
    key_prefix, plain_token = build_api_key_plaintext()
    db_api_key = crud_api_key.rotate_api_key_secret(
        db,
        api_key_id,
        key_prefix=key_prefix,
        secret_hash=hash_api_key_secret(plain_token),
        expires_at=expires_at,
    )
    if db_api_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    write_api_key_audit_log(
        "rotated",
        {
            "key_prefix": db_api_key.key_prefix,
            "operator_user_id": current_user.id,
            "ip": get_client_ip(request),
        },
    )
    return JSONResponse(
        {
            "success": True,
            "message": "API Key 已轮换，请立即保存新的明文密钥",
            "plain_token": plain_token,
            "api_key": {
                "id": db_api_key.id,
                "name": db_api_key.name,
                "key_prefix": db_api_key.key_prefix,
                "access_level": db_api_key.access_level,
                "status": db_api_key.status,
            },
        }
    )


async def delete_api_key_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    api_key_id: int,
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    db_api_key = crud_api_key.get_api_key(db, api_key_id)
    if db_api_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    deleted = crud_api_key.delete_api_key(db, api_key_id)
    write_api_key_audit_log(
        "deleted",
        {
            "key_prefix": getattr(deleted, "key_prefix", ""),
            "operator_user_id": current_user.id,
            "ip": get_client_ip(request),
        },
    )
    return {"success": True, "message": "API Key 已删除"}


async def update_api_key_action(
    request: Request,
    db: Session,
    current_user: User,
    *,
    api_key_id: int,
    name: Optional[str],
    access_level: Optional[str],
    notes: Optional[str],
    expires_at_text: Optional[str],
    csrf_token: str,
):
    ensure_admin_user(current_user)
    verify_csrf_token(request, csrf_token)

    expires_at = None
    raw_expires_at = str(expires_at_text or "").strip()
    if raw_expires_at:
        try:
            from datetime import datetime

            expires_at = datetime.fromisoformat(raw_expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="过期时间格式不正确") from exc

    payload = ApiKeyUpdate(
        name=name,
        access_level=access_level,
        notes=notes,
        expires_at=expires_at,
    )
    db_api_key = crud_api_key.update_api_key(db, api_key_id, payload)
    if db_api_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    return {"success": True, "message": "API Key 已更新"}
