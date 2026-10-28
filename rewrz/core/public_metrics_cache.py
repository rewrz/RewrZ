from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..crud import setting as crud_setting
from ..schemas.setting import SettingCreate, SettingUpdate


HOMEPAGE_STATS_CACHE_KEY = "public_homepage_stats_cache"
FORMAT_ARCHIVE_STATS_CACHE_PREFIX = "public_format_archive_stats_cache"
PUBLIC_METRICS_CACHE_TTL_SECONDS = 900
LOCAL_MEMORY_CACHE_MAX_TTL_SECONDS = 60

_local_cache: dict[str, tuple[float, dict]] = {}
_local_cache_locks: dict[str, threading.Lock] = {}
_local_cache_guard = threading.Lock()
_refresh_inflight: set[str] = set()


def _get_key_lock(cache_key: str) -> threading.Lock:
    with _local_cache_guard:
        lock = _local_cache_locks.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _local_cache_locks[cache_key] = lock
        return lock


def _read_local_cache(cache_key: str) -> dict | None:
    now = time.monotonic()
    with _local_cache_guard:
        cached = _local_cache.get(cache_key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _local_cache.pop(cache_key, None)
            return None
        return dict(payload)


def _write_local_cache(cache_key: str, payload: dict, ttl_seconds: int) -> None:
    memory_ttl = max(1, min(int(ttl_seconds or 0), LOCAL_MEMORY_CACHE_MAX_TTL_SECONDS))
    with _local_cache_guard:
        _local_cache[cache_key] = (time.monotonic() + memory_ttl, dict(payload))


def _clear_local_cache(cache_keys: Iterable[str] | None = None) -> None:
    with _local_cache_guard:
        if cache_keys is None:
            _local_cache.clear()
            return
        for cache_key in cache_keys:
            _local_cache.pop(cache_key, None)


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
        try:
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
        except IntegrityError:
            # 多 worker 同时冷启动时只有一个进程能插入成功，其余进程改为更新。
            db.rollback()
            existing = crud_setting.get_setting(db, cache_key)
            if existing is None:
                raise

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


def _schedule_snapshot_refresh(
    *,
    cache_key: str,
    loader: Callable[[Session], dict],
    ttl_seconds: int,
    description: str,
    bind,
) -> None:
    """返回过期快照的同时在后台刷新，避免请求同步执行聚合查询。"""
    with _local_cache_guard:
        if cache_key in _refresh_inflight:
            return
        _refresh_inflight.add(cache_key)

    def _worker() -> None:
        session = None
        try:
            session = sessionmaker(bind=bind, autocommit=False, autoflush=False)()
            payload = dict(loader(session) or {})
            now_utc = _now_utc()
            payload["checked_at_iso"] = now_utc.isoformat()
            payload["checked_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            payload["cache_hit"] = False
            _save_cache_payload(session, cache_key, payload, description)
            _write_local_cache(cache_key, payload, ttl_seconds)
        except Exception:
            # 后台刷新失败保留旧快照，下一次请求会再次触发
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            with _local_cache_guard:
                _refresh_inflight.discard(cache_key)

    thread = threading.Thread(
        target=_worker,
        name=f"public-metrics-{cache_key[-12:]}",
        daemon=True,
    )
    try:
        thread.start()
    except RuntimeError:
        with _local_cache_guard:
            _refresh_inflight.discard(cache_key)


def get_homepage_stats_snapshot(
    db: Session,
    *,
    loader: Callable[[Session], dict],
    ttl_seconds: int = PUBLIC_METRICS_CACHE_TTL_SECONDS,
) -> dict:
    local_cached = _read_local_cache(HOMEPAGE_STATS_CACHE_KEY)
    if local_cached is not None:
        return {
            **local_cached,
            "cache_hit": True,
        }

    cached = _load_cache_payload(db, HOMEPAGE_STATS_CACHE_KEY)
    if _is_cache_fresh(cached, ttl_seconds=ttl_seconds):
        _write_local_cache(HOMEPAGE_STATS_CACHE_KEY, cached, ttl_seconds)
        return {
            **cached,
            "cache_hit": True,
        }

    if cached:
        # 过期快照先返回给页面，刷新交给后台线程，请求不再同步跑聚合统计
        _schedule_snapshot_refresh(
            cache_key=HOMEPAGE_STATS_CACHE_KEY,
            loader=loader,
            ttl_seconds=ttl_seconds,
            description="前台首页聚合统计缓存",
            bind=db.get_bind(),
        )
        return {
            **cached,
            "cache_hit": True,
            "stale": True,
        }

    with _get_key_lock(HOMEPAGE_STATS_CACHE_KEY):
        local_cached = _read_local_cache(HOMEPAGE_STATS_CACHE_KEY)
        if local_cached is not None:
            return {
                **local_cached,
                "cache_hit": True,
            }

        payload = dict(loader(db) or {})
        now_utc = _now_utc()
        payload["checked_at_iso"] = now_utc.isoformat()
        payload["checked_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        payload["cache_hit"] = False
        _save_cache_payload(db, HOMEPAGE_STATS_CACHE_KEY, payload, "前台首页聚合统计缓存")
        _write_local_cache(HOMEPAGE_STATS_CACHE_KEY, payload, ttl_seconds)
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
    local_cached = _read_local_cache(cache_key)
    if local_cached is not None:
        return {
            **local_cached,
            "cache_hit": True,
        }

    cached = _load_cache_payload(db, cache_key)
    if _is_cache_fresh(cached, ttl_seconds=ttl_seconds):
        _write_local_cache(cache_key, cached, ttl_seconds)
        return {
            **cached,
            "cache_hit": True,
        }

    if cached:
        # 过期快照先返回给页面，刷新交给后台线程，请求不再同步跑聚合统计
        _schedule_snapshot_refresh(
            cache_key=cache_key,
            loader=loader,
            ttl_seconds=ttl_seconds,
            description="前台格式归档聚合统计缓存",
            bind=db.get_bind(),
        )
        return {
            **cached,
            "cache_hit": True,
            "stale": True,
        }

    with _get_key_lock(cache_key):
        local_cached = _read_local_cache(cache_key)
        if local_cached is not None:
            return {
                **local_cached,
                "cache_hit": True,
            }

        payload = dict(loader(db) or {})
        now_utc = _now_utc()
        payload["checked_at_iso"] = now_utc.isoformat()
        payload["checked_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        payload["cache_hit"] = False
        _save_cache_payload(db, cache_key, payload, "前台格式归档聚合统计缓存")
        _write_local_cache(cache_key, payload, ttl_seconds)
        return payload


def clear_public_metrics_memory_cache() -> None:
    """清空进程内统计缓存，供配置变更与测试使用。"""
    _clear_local_cache()


def invalidate_public_metrics_cache(db: Session, *, extra_keys: List[str] | None = None) -> None:
    keys = [HOMEPAGE_STATS_CACHE_KEY]
    keys.extend(list(extra_keys or []))
    _clear_local_cache(keys)
    for cache_key in keys:
        try:
            crud_setting.delete_setting(db, cache_key)
        except Exception:
            db.rollback()
