from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List

from sqlalchemy.orm import Session

from ..crud import setting as crud_setting
from ..schemas.setting import SettingCreate, SettingUpdate


HOMEPAGE_STATS_CACHE_KEY = "public_homepage_stats_cache"
FORMAT_ARCHIVE_STATS_CACHE_PREFIX = "public_format_archive_stats_cache"
PUBLIC_METRICS_CACHE_TTL_SECONDS = 900


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_cache_payload(db: Session, cache_key: str) -> dict | None:
    setting = crud_setting.get_setting(db, cache_key)
    if setting is None or not isinstance(setting.value, dict):
        return None
    payload = setting.value.get("value")
    return payload if isinstance(payload, dict) else None


def _save_cache_payload(db: Session, cache_key: str, payload: dict, description: str) -> None:
    normalized_payload = {"value": payload}
    existing = crud_setting.get_setting(db, cache_key)
    if existing is None:
        crud_setting.create_setting(
            db,
            SettingCreate(
                key=cache_key,
                value=normalized_payload,
                description=description,
                category="system",
                type="json",
            ),
        )
        return

    crud_setting.update_setting(
        db,
        cache_key,
        SettingUpdate(
            value=normalized_payload,
            description=description,
            category="system",
            type="json",
        ),
    )


def _is_cache_fresh(cached: dict | None, *, ttl_seconds: int, now: datetime | None = None) -> bool:
    if not cached:
        return False
    checked_at_iso = str(cached.get("checked_at_iso", "") or "").strip()
    if not checked_at_iso:
        return False
    try:
        checked_at = datetime.fromisoformat(checked_at_iso)
    except ValueError:
        return False
    current = now or _now_utc()
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return (current - checked_at).total_seconds() < max(30, int(ttl_seconds or PUBLIC_METRICS_CACHE_TTL_SECONDS))


def get_homepage_stats_snapshot(
    db: Session,
    *,
    loader: Callable[[Session], dict],
    ttl_seconds: int = PUBLIC_METRICS_CACHE_TTL_SECONDS,
) -> dict:
    cached = _load_cache_payload(db, HOMEPAGE_STATS_CACHE_KEY)
    if _is_cache_fresh(cached, ttl_seconds=ttl_seconds):
        return {
            **cached,
            "cache_hit": True,
        }

    payload = dict(loader(db) or {})
    now_utc = _now_utc()
    payload["checked_at_iso"] = now_utc.isoformat()
    payload["checked_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    payload["cache_hit"] = False
    _save_cache_payload(db, HOMEPAGE_STATS_CACHE_KEY, payload, "前台首页聚合统计缓存")
    return payload


def build_format_archive_cache_key(
    format_slug: str,
    *,
    exclude_format_ids: Iterable[int] | None = None,
) -> str:
    normalized_slug = str(format_slug or "").strip().lower() or "unknown"
    exclude_ids = sorted({int(item) for item in (exclude_format_ids or []) if int(item) > 0})
    if not exclude_ids:
        return f"{FORMAT_ARCHIVE_STATS_CACHE_PREFIX}:{normalized_slug}"
    suffix = ",".join(str(item) for item in exclude_ids)
    return f"{FORMAT_ARCHIVE_STATS_CACHE_PREFIX}:{normalized_slug}:{suffix}"


def get_format_archive_stats_snapshot(
    db: Session,
    *,
    cache_key: str,
    loader: Callable[[Session], dict],
    ttl_seconds: int = PUBLIC_METRICS_CACHE_TTL_SECONDS,
) -> dict:
    cached = _load_cache_payload(db, cache_key)
    if _is_cache_fresh(cached, ttl_seconds=ttl_seconds):
        return {
            **cached,
            "cache_hit": True,
        }

    payload = dict(loader(db) or {})
    now_utc = _now_utc()
    payload["checked_at_iso"] = now_utc.isoformat()
    payload["checked_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    payload["cache_hit"] = False
    _save_cache_payload(db, cache_key, payload, "前台格式归档聚合统计缓存")
    return payload


def invalidate_public_metrics_cache(db: Session, *, extra_keys: List[str] | None = None) -> None:
    keys = [HOMEPAGE_STATS_CACHE_KEY]
    keys.extend(list(extra_keys or []))
    for cache_key in keys:
        try:
            crud_setting.delete_setting(db, cache_key)
        except Exception:
            db.rollback()
