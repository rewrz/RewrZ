from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import ApiKey
from ..schemas import ApiKeyCreate, ApiKeyUpdate


def get_api_key(db: Session, api_key_id: int) -> Optional[ApiKey]:
    return db.execute(
        select(ApiKey)
        .options(joinedload(ApiKey.created_by))
        .filter(ApiKey.id == api_key_id)
    ).scalar_one_or_none()


def get_api_key_by_prefix(db: Session, key_prefix: str) -> Optional[ApiKey]:
    return db.execute(
        select(ApiKey)
        .options(joinedload(ApiKey.created_by))
        .filter(ApiKey.key_prefix == key_prefix)
    ).scalar_one_or_none()


def get_api_keys(db: Session):
    return db.execute(
        select(ApiKey)
        .options(joinedload(ApiKey.created_by))
        .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
    ).scalars().all()


def create_api_key(
    db: Session,
    payload: ApiKeyCreate,
    *,
    key_prefix: str,
    secret_hash: str,
    created_by_user_id: Optional[int],
) -> ApiKey:
    db_api_key = ApiKey(
        name=payload.name,
        key_prefix=key_prefix,
        secret_hash=secret_hash,
        access_level=payload.access_level,
        status="active",
        expires_at=payload.expires_at,
        notes=payload.notes,
        created_by_user_id=created_by_user_id,
    )
    db.add(db_api_key)
    db.commit()
    db.refresh(db_api_key)
    return db_api_key


def update_api_key(db: Session, api_key_id: int, payload: ApiKeyUpdate) -> Optional[ApiKey]:
    db_api_key = get_api_key(db, api_key_id)
    if db_api_key is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_api_key, key, value)

    db.commit()
    db.refresh(db_api_key)
    return db_api_key


def update_api_key_status(db: Session, api_key_id: int, status: str) -> Optional[ApiKey]:
    db_api_key = get_api_key(db, api_key_id)
    if db_api_key is None:
        return None
    db_api_key.status = str(status or "").strip().lower()
    db.commit()
    db.refresh(db_api_key)
    return db_api_key


def rotate_api_key_secret(
    db: Session,
    api_key_id: int,
    *,
    key_prefix: str,
    secret_hash: str,
    expires_at: Optional[datetime] = None,
) -> Optional[ApiKey]:
    db_api_key = get_api_key(db, api_key_id)
    if db_api_key is None:
        return None
    db_api_key.key_prefix = key_prefix
    db_api_key.secret_hash = secret_hash
    db_api_key.status = "active"
    db_api_key.expires_at = expires_at
    db.commit()
    db.refresh(db_api_key)
    return db_api_key


def touch_api_key_usage(db: Session, api_key_id: int, *, used_ip: str) -> Optional[ApiKey]:
    db_api_key = get_api_key(db, api_key_id)
    if db_api_key is None:
        return None
    db_api_key.last_used_at = datetime.now()
    db_api_key.last_used_ip = (used_ip or "").strip()[:128] or None
    db.commit()
    db.refresh(db_api_key)
    return db_api_key


def delete_api_key(db: Session, api_key_id: int) -> Optional[ApiKey]:
    db_api_key = get_api_key(db, api_key_id)
    if db_api_key is None:
        return None
    db.delete(db_api_key)
    db.commit()
    return db_api_key
