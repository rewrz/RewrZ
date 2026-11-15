"""文章浏览量内存计数与批量落库。

详情页每次访问都同步执行 UPDATE settings + commit，会让“读多写少”的博客在
并发上来时被写锁拖住。这里改为：访问只累加到进程内存，后台线程每 15 秒
把增量按批合并写库（每批独立提交，缩小写锁窗口），页面展示沿用查询时
已附加的 views_count，允许短暂滞后（最多一个刷新周期）。

浏览量不再写 settings：配置表按文章数一行行膨胀后，设置读取与
`key LIKE 'post_views_count_%'` 统计都会被拖慢。指标统一落在
`post_view_stats`，写入走多行 upsert，读取按主键批量直取。
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Iterable, List

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import PostViewStat
from .database import db_manager
from .db_write_gate import background_write_gate

logger = logging.getLogger(__name__)

# 批量落库间隔：15 秒足以把突发访问合并成极少量的写事务，
# 又不会让浏览量在页面上明显滞后。
FLUSH_INTERVAL_SECONDS = 15

# 与访问统计刷写（同样 15 秒一次）错开半拍，避免两次后台写在同一时刻
# 争抢 SQLite 写锁，放大 WAL checkpoint 期间的等待时间。
FLUSH_INITIAL_OFFSET_SECONDS = 7

# 单条 upsert 最多合并多少行。SQLite 旧版本的绑定参数上限是 999，
# 每行 2 个参数时 300 行是安全线，也避免单条 SQL 过大导致编译与写锁时间变长。
_UPSERT_CHUNK_SIZE = 300

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
    if not pending:
        return
    with _LOCK:
        for post_id, count in pending.items():
            _PENDING[post_id] = _PENDING.get(post_id, 0) + count


def _normalize_post_ids(post_ids: Iterable[int]) -> List[int]:
    normalized = set()
    for post_id in post_ids or []:
        try:
            value = int(post_id)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized.add(value)
    return sorted(normalized)


def load_post_views_map(
    db: Session,
    post_ids: Iterable[int],
    *,
    chunk_size: int = 300,
) -> Dict[int, int]:
    """按文章 ID 批量读取浏览量，缺失的文章不出现在结果里。"""
    normalized_ids = _normalize_post_ids(post_ids)
    if not normalized_ids:
        return {}

    views_map: Dict[int, int] = {}
    batch_size = max(1, int(chunk_size or 300))
    table = PostViewStat.__table__
    for offset in range(0, len(normalized_ids), batch_size):
        batch = normalized_ids[offset : offset + batch_size]
        rows = db.execute(
            select(table.c.post_id, table.c.views).where(table.c.post_id.in_(batch))
        ).all()
        for post_id, views in rows:
            try:
                views_map[int(post_id)] = max(0, int(views or 0))
            except (TypeError, ValueError):
                continue
    return views_map


def sum_post_views(db: Session) -> int:
    """全站浏览量总和。"""
    total = db.execute(select(func.coalesce(func.sum(PostViewStat.views), 0))).scalar_one()
    try:
        return max(0, int(total or 0))
    except (TypeError, ValueError):
        return 0


def delete_post_view_stats(db: Session, post_ids: Iterable[int]) -> None:
    """删除指定文章的浏览量指标行（不提交事务，由调用方控制提交）。"""
    normalized_ids = _normalize_post_ids(post_ids)
    if not normalized_ids:
        return
    for offset in range(0, len(normalized_ids), 300):
        batch = normalized_ids[offset : offset + 300]
        db.execute(delete(PostViewStat).where(PostViewStat.post_id.in_(batch)))


def _build_upsert_statement(dialect_name: str, rows: List[dict]):
    """按数据库类型生成多行累加 upsert 语句。"""
    table = PostViewStat.__table__
    if dialect_name == "postgresql":
        statement = postgresql_insert(table).values(rows)
    else:
        statement = sqlite_insert(table).values(rows)
    return statement.on_conflict_do_update(
        index_elements=[table.c.post_id],
        set_={
            "views": table.c.views + statement.excluded.views,
            "updated_at": func.now(),
        },
    )


def _upsert_chunk(db: Session, dialect_name: str, chunk: Dict[int, int]) -> int:
    rows = [
        {"post_id": int(post_id), "views": int(count)}
        for post_id, count in chunk.items()
        if int(count) > 0
    ]
    if not rows:
        return 0
    db.execute(_build_upsert_statement(dialect_name, rows))
    return len(rows)


def flush_post_views() -> int:
    """把待写增量批量落库，返回成功写入的文章数量。

    每批独立提交：单条语句更小、写锁窗口更短，批次之间即使失败也只需回填
    未写入的增量，不会因为一条坏数据让整轮全部重来。
    """
    with _LOCK:
        if not _PENDING:
            return 0
        # 必须复制：_PENDING.clear() 会清空同一个字典，直接引用会导致本轮什么都不写
        pending = dict(_PENDING)
        _PENDING.clear()

    if not pending:
        return 0

    # 与访问统计刷写串行：SQLite 只有一个写者，排队比互相等待锁更可控。
    with background_write_gate() as acquired:
        if not acquired:
            _merge_back(pending)
            return 0

        db = db_manager.get_session()
        if db is None:
            _merge_back(pending)
            return 0

        items = list(pending.items())
        written = 0
        try:
            try:
                dialect_name = str(db.get_bind().dialect.name or "").lower()
            except Exception:
                dialect_name = "sqlite"

            for offset in range(0, len(items), _UPSERT_CHUNK_SIZE):
                chunk = dict(items[offset : offset + _UPSERT_CHUNK_SIZE])
                try:
                    chunk_written = _upsert_chunk(db, dialect_name, chunk)
                    db.commit()
                    # 提交成功后才计入，避免提交失败时返回值虚高
                    written += chunk_written
                except Exception as exc:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    # 当前批次与后续批次都还没写入，统一回填
                    _merge_back(dict(items[offset:]))
                    logger.warning("浏览量批量落库失败，已留待下次重试：%s", exc)
                    break
            return written
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
