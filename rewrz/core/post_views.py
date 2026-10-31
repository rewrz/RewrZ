"""文章浏览量内存计数与批量落库。

详情页每次访问都同步执行 UPDATE settings + commit，会让“读多写少”的博客在
并发上来时被写锁拖住。这里改为：访问只累加到进程内存，后台线程每 15 秒
把增量合并成一次事务写库，页面展示沿用查询时已附加的 views_count，
允许短暂滞后（最多一个刷新周期）。
"""
from __future__ import annotations

import logging
import threading
from typing import Dict

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .database import db_manager

logger = logging.getLogger(__name__)

# 批量落库间隔：15 秒足以把突发访问合并成极少量的写事务，
# 又不会让浏览量在页面上明显滞后。
FLUSH_INTERVAL_SECONDS = 15

# 与访问统计刷写（同样 15 秒一次）错开半拍，避免两次后台写在同一时刻
# 争抢 SQLite 写锁，放大 WAL checkpoint 期间的等待时间。
FLUSH_INITIAL_OFFSET_SECONDS = 7

_PENDING: Dict[int, int] = {}
_LOCK = threading.Lock()
_FLUSH_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def increment_post_views(post_id: int, step: int = 1) -> None:
    """记录一次浏览量增量，只操作内存，不做任何数据库读写。"""
    try:
        normalized_id = int(post_id)
    except (TypeError, ValueError):
        return
    if normalized_id <= 0:
        return
    increment = max(1, int(step or 1))
    with _LOCK:
        _PENDING[normalized_id] = _PENDING.get(normalized_id, 0) + increment


def get_pending_views(post_id: int) -> int:
    """读取尚未落库的增量，供测试与调试使用。"""
    with _LOCK:
        return _PENDING.get(int(post_id), 0)


def discard_post_views(post_id: int) -> None:
    """内容被删除时丢弃尚未落库的增量，避免已删除内容的指标行被重新创建。"""
    try:
        normalized_id = int(post_id)
    except (TypeError, ValueError):
        return
    with _LOCK:
        _PENDING.pop(normalized_id, None)


def _merge_back(pending: Dict[int, int]) -> None:
    """落库失败时把增量合并回待写队列，等待下一轮重试。"""
    with _LOCK:
        for post_id, count in pending.items():
            _PENDING[post_id] = _PENDING.get(post_id, 0) + count


def _build_upsert_statement(dialect_name: str):
    """按数据库类型生成浏览量原子 UPSERT 语句。"""
    if dialect_name == "postgresql":
        return text(
            """
            INSERT INTO settings (key, value, description, category, type, created_at, updated_at)
            VALUES (
                :key,
                jsonb_build_object('value', :step)::json,
                'Post views metric',
                'post_metrics',
                'integer',
                (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
                (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
            )
            ON CONFLICT (key) DO UPDATE SET
                value = (
                    COALESCE(settings.value::jsonb, '{}'::jsonb)
                    || jsonb_build_object(
                        'value',
                        COALESCE((settings.value ->> 'value')::int, 0) + :step
                    )
                )::json,
                updated_at = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
            """
        )
    return text(
        """
        INSERT INTO settings (key, value, description, category, type, created_at, updated_at)
        VALUES (
            :key,
            json_object('value', :step),
            'Post views metric',
            'post_metrics',
            'integer',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (key) DO UPDATE SET
            value = json_set(
                CASE
                    WHEN json_valid(settings.value) THEN settings.value
                    ELSE json_object('value', 0)
                END,
                '$.value',
                COALESCE(
                    json_extract(
                        CASE
                            WHEN json_valid(settings.value) THEN settings.value
                            ELSE json_object('value', 0)
                        END,
                        '$.value'
                    ),
                    0
                ) + :step
            ),
            updated_at = CURRENT_TIMESTAMP
        """
    )


def flush_post_views() -> int:
    """把待写增量批量落库，返回成功写入的文章数量。

    单事务提交，任意一步失败都整体回滚并把增量合并回队列，下一轮重试。
    """
    with _LOCK:
        if not _PENDING:
            return 0
        # 必须复制：_PENDING.clear() 会清空同一个字典，直接引用会导致本轮什么都不写
        pending = dict(_PENDING)
        _PENDING.clear()

    db = db_manager.get_session()
    if db is None:
        _merge_back(pending)
        return 0

    try:
        try:
            dialect_name = str(db.get_bind().dialect.name or "").lower()
        except Exception:
            dialect_name = "sqlite"
        statement = _build_upsert_statement(dialect_name)
        for post_id, count in pending.items():
            db.execute(
                statement,
                {"step": int(count), "key": f"post_views_count_{post_id}"},
            )
        db.commit()
        return len(pending)
    except IntegrityError:
        db.rollback()
        _merge_back(pending)
        return 0
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        _merge_back(pending)
        logger.warning("浏览量批量落库失败，已留待下次重试：%s", exc)
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


def _flush_loop() -> None:
    """后台刷新线程：按固定间隔落库，进程退出时由 stop 唤醒。"""
    if _STOP_EVENT.wait(FLUSH_INITIAL_OFFSET_SECONDS):
        return
    while not _STOP_EVENT.wait(FLUSH_INTERVAL_SECONDS):
        try:
            flush_post_views()
        except Exception:
            logger.exception("浏览量批量落库线程异常")


def start_post_views_flusher() -> None:
    """启动后台刷新线程（幂等）。"""
    global _FLUSH_THREAD
    if _FLUSH_THREAD is not None and _FLUSH_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _FLUSH_THREAD = threading.Thread(
        target=_flush_loop,
        name="rewrz-post-views-flusher",
        daemon=True,
    )
    _FLUSH_THREAD.start()


def stop_post_views_flusher() -> None:
    """停止刷新线程并做最后一次落库。"""
    global _FLUSH_THREAD
    _STOP_EVENT.set()
    thread = _FLUSH_THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout=5)
    _FLUSH_THREAD = None
    try:
        flush_post_views()
    except Exception:
        logger.exception("退出前浏览量落库失败")
