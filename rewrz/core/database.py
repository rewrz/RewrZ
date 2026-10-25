import os
import shutil
import sqlite3
import threading
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from starlette.requests import Request
from ..models.base import Base
from .config import settings

VALID_SQLITE_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}


def _is_sqlite_url(database_url: str) -> bool:
    return str(database_url or "").strip().lower().startswith("sqlite")


def _is_memory_sqlite_url(database_url: str) -> bool:
    normalized = str(database_url or "").strip().lower()
    return normalized in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in normalized


def resolve_sqlite_database_path(bind) -> str | None:
    """解析 SQLAlchemy 引擎/连接对应的 SQLite 文件绝对路径。

    非 SQLite、内存数据库或无法解析时返回 None。相对路径按进程当前工作目录解析，
    与 SQLite 引擎的实际行为保持一致。
    """
    url = getattr(bind, "url", None)
    if url is None:
        url = getattr(getattr(bind, "engine", None), "url", None)
    if url is None:
        return None

    get_backend_name = getattr(url, "get_backend_name", None)
    if not callable(get_backend_name):
        return None
    try:
        backend_name = str(get_backend_name() or "").lower()
    except Exception:
        return None
    if backend_name != "sqlite":
        return None

    raw_path = str(getattr(url, "database", "") or "").strip()
    if not raw_path or ":memory:" in raw_path:
        return None
    return os.path.abspath(os.path.expanduser(raw_path))


class DatabaseManager:
    """数据库连接管理器，支持动态重新初始化"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
        self._pool_timeout_count = 0
        self._pool_timeout_lock = threading.Lock()
        self.initialize()
    
    def initialize(self) -> bool:
        """初始化或重新初始化数据库连接"""
        if settings.installation_complete and settings.DATABASE_URL:
            # 清理旧连接
            if self.engine:
                self.engine.dispose()
            
            database_url = settings.DATABASE_URL
            is_sqlite = _is_sqlite_url(database_url)
            if is_sqlite:
                # 本地 SQLite 文件不存在网络断连，预检查与连接回收只会白耗查询；
                # 页缓存由 SQLITE_CACHE_SIZE_KIB 控制，避免池大后内存失控。
                engine_kwargs = {"pool_pre_ping": False}
            else:
                engine_kwargs = {
                    "pool_pre_ping": bool(getattr(settings, "DB_POOL_PRE_PING", True)),
                    "pool_recycle": int(getattr(settings, "DB_POOL_RECYCLE", 1800)),
                }
            if not (is_sqlite and _is_memory_sqlite_url(database_url)):
                engine_kwargs.update({
                    "pool_size": int(getattr(settings, "DB_POOL_SIZE", 10)),
                    "max_overflow": int(getattr(settings, "DB_MAX_OVERFLOW", 20)),
                    "pool_timeout": int(getattr(settings, "DB_POOL_TIMEOUT", 10)),
                })
            if is_sqlite:
                engine_kwargs["connect_args"] = {
                    "check_same_thread": False,
                    "timeout": max(1, int(getattr(settings, "SQLITE_BUSY_TIMEOUT_MS", 30000) or 30000)) / 1000,
                }

            self.engine = create_engine(database_url, **engine_kwargs)
            if is_sqlite:
                self._configure_sqlite(self.engine)
            self.SessionLocal = sessionmaker(
                autocommit=False, 
                autoflush=False, 
                bind=self.engine
            )
            self._initialized = True
            return True
        return False

    @staticmethod
    def _configure_sqlite(engine) -> None:
        journal_mode = str(getattr(settings, "SQLITE_JOURNAL_MODE", "WAL") or "WAL").strip().upper()
        if journal_mode not in VALID_SQLITE_JOURNAL_MODES:
            journal_mode = "WAL"
        busy_timeout_ms = max(1000, int(getattr(settings, "SQLITE_BUSY_TIMEOUT_MS", 30000) or 30000))
        cache_size_kib = max(256, int(getattr(settings, "SQLITE_CACHE_SIZE_KIB", 1024) or 1024))
        synchronous = str(getattr(settings, "SQLITE_SYNCHRONOUS", "NORMAL") or "NORMAL").strip().upper()
        if synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            synchronous = "NORMAL"

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
                cursor.execute(f"PRAGMA journal_mode={journal_mode}")
                # 负值表示 KiB：限制每个连接的页缓存，连接池放大后内存仍可控
                cursor.execute(f"PRAGMA cache_size=-{cache_size_kib}")
                cursor.execute(f"PRAGMA synchronous={synchronous}")
            finally:
                cursor.close()

    def get_pool_status(self) -> dict:
        """返回连接池使用情况，供异常日志和排障使用。"""
        if not self.engine:
            return {}
        pool = self.engine.pool
        status = {}
        for key, method_name in (
            ("size", "size"),
            ("checked_in", "checkedin"),
            ("checked_out", "checkedout"),
            ("overflow", "overflow"),
        ):
            method = getattr(pool, method_name, None)
            if callable(method):
                try:
                    status[key] = method()
                except Exception:
                    continue
        status["timeout_seconds"] = int(getattr(settings, "DB_POOL_TIMEOUT", 10) or 10)
        with self._pool_timeout_lock:
            status["timeout_count"] = self._pool_timeout_count
        return status

    def record_pool_timeout(self) -> int:
        """记录一次连接池等待超时，便于从日志和状态接口观察发生频率。"""
        with self._pool_timeout_lock:
            self._pool_timeout_count += 1
            return self._pool_timeout_count

    def reload_if_needed(self) -> bool:
        """检查配置变化并重新加载"""
        if settings.reload_config():
            return self.initialize()
        return self._initialized
    
    def get_session(self):
        """获取数据库会话"""
        if self._initialized and self.SessionLocal:
            return self.SessionLocal()
        return None
    
    @property
    def is_available(self) -> bool:
        """数据库是否可用"""
        return self._initialized and self.engine is not None

# 全局数据库管理器实例
db_manager = DatabaseManager()

# VACUUM 会重建数据库文件，同一进程内不允许并发执行
_DB_VACUUM_LOCK = threading.Lock()


def get_sqlite_database_path(bind=None) -> str | None:
    """返回数据库连接对应的 SQLite 文件绝对路径；未指定时使用全局引擎。"""
    if bind is None:
        if not db_manager.is_available or db_manager.engine is None:
            return None
        bind = db_manager.engine
    return resolve_sqlite_database_path(bind)


# VACUUM 需要约两倍数据库大小的临时空间，低于该倍数就无法安全压缩
SQLITE_VACUUM_SPACE_FACTOR = 2
# 低于四倍空间时提前预警，避免拖到无法压缩
SQLITE_VACUUM_WARN_FACTOR = 4
# 可回收空间达到 16MB 且占文件 10% 以上时才提示压缩，避免小库误报
SQLITE_RECLAIM_MIN_BYTES = 16 * 1024 * 1024
SQLITE_RECLAIM_MIN_RATIO = 0.10


def get_sqlite_storage_status(bind=None) -> dict | None:
    """返回 SQLite 文件占用、空闲页和磁盘余量，用于后台压缩预警。"""
    database_path = get_sqlite_database_path(bind)
    if not database_path or not os.path.exists(database_path):
        return None

    try:
        size_bytes = os.path.getsize(database_path)
    except OSError:
        return None
    page_size = 0
    page_count = 0
    free_pages = 0
    try:
        connection = sqlite3.connect(database_path, timeout=2, isolation_level=None)
        try:
            connection.execute("PRAGMA query_only=ON")
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        # 读取失败不能影响后台其他统计，按暂无空闲页处理
        pass

    reclaimable_bytes = page_size * free_pages
    free_page_ratio = (free_pages / page_count) if page_count else 0.0
    try:
        disk_free_bytes = shutil.disk_usage(os.path.dirname(database_path)).free
    except OSError:
        return None
    vacuum_required_bytes = size_bytes * SQLITE_VACUUM_SPACE_FACTOR
    vacuum_possible = disk_free_bytes >= vacuum_required_bytes
    reclaim_warn_bytes = max(SQLITE_RECLAIM_MIN_BYTES, size_bytes * SQLITE_RECLAIM_MIN_RATIO)
    should_reclaim = reclaimable_bytes >= reclaim_warn_bytes

    level = "ok"
    message = ""
    if not vacuum_possible:
        level = "critical"
        message = (
            f"磁盘剩余空间不足，当前无法安全压缩数据库："
            f"至少需要 {_format_size(vacuum_required_bytes)}，可用 {_format_size(disk_free_bytes)}。"
            f"请先清理磁盘或扩容。"
        )
    elif disk_free_bytes < size_bytes * SQLITE_VACUUM_WARN_FACTOR:
        level = "warning"
        if should_reclaim:
            message = (
                f"磁盘余量偏低（数据库 {_format_size(size_bytes)}，可用 {_format_size(disk_free_bytes)}），"
                f"数据库还有 {_format_size(reclaimable_bytes)} 空闲页可回收，建议尽快压缩。"
            )
        else:
            message = (
                f"磁盘余量偏低（数据库 {_format_size(size_bytes)}，可用 {_format_size(disk_free_bytes)}），"
                f"数据库暂无可回收空闲页，请清理磁盘或扩容。"
            )
    elif should_reclaim:
        level = "warning"
        message = (
            f"数据库有 {_format_size(reclaimable_bytes)} 空闲页可回收，"
            f"建议压缩数据库释放磁盘空间。"
        )

    return {
        "path": database_path,
        "size_bytes": size_bytes,
        "size": _format_size(size_bytes),
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable": _format_size(reclaimable_bytes),
        "free_page_ratio": round(free_page_ratio, 4),
        "disk_free_bytes": disk_free_bytes,
        "disk_free": _format_size(disk_free_bytes),
        "vacuum_required_bytes": vacuum_required_bytes,
        "vacuum_required": _format_size(vacuum_required_bytes),
        "vacuum_possible": vacuum_possible,
        "level": level,
        "message": message,
    }


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    return f"{num_bytes / 1024:.1f} KB"


def vacuum_sqlite_database() -> dict:
    """压缩 SQLite 数据库，回收已删除数据留下的空闲页。

    VACUUM 会重建数据库文件，执行期间写入会被阻塞，且临时文件需要额外磁盘空间。
    因此先做容量检查，再用独立的 sqlite3 连接执行，避免受 SQLAlchemy 事务状态影响。
    """
    database_path = get_sqlite_database_path()
    if not database_path:
        raise RuntimeError("当前数据库不是本地 SQLite 文件，无法执行压缩。")
    if not os.path.exists(database_path):
        raise RuntimeError("数据库文件不存在，无法执行压缩。")
    if not _DB_VACUUM_LOCK.acquire(blocking=False):
        raise RuntimeError("已有数据库压缩任务正在执行，请稍后再试。")

    try:
        try:
            size_before = os.path.getsize(database_path)
            free_disk = shutil.disk_usage(os.path.dirname(database_path)).free
        except OSError as exc:
            raise RuntimeError(f"读取数据库或磁盘信息失败：{exc}") from exc

        required_free = size_before * SQLITE_VACUUM_SPACE_FACTOR
        if free_disk < required_free:
            raise RuntimeError(
                f"磁盘剩余空间不足：压缩至少需要 {_format_size(required_free)}，"
                f"当前可用 {_format_size(free_disk)}。"
            )

        timeout_ms = max(1000, int(getattr(settings, "SQLITE_BUSY_TIMEOUT_MS", 30000) or 30000))
        started_at = time.perf_counter()
        try:
            connection = sqlite3.connect(
                database_path,
                timeout=timeout_ms / 1000,
                isolation_level=None,
            )
        except sqlite3.Error as exc:
            raise RuntimeError(f"无法连接数据库：{exc}") from exc

        try:
            connection.execute(f"PRAGMA busy_timeout={timeout_ms}")
            free_pages_before = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            checkpoint_busy = False
            try:
                checkpoint_row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                checkpoint_busy = bool(checkpoint_row and checkpoint_row[0])
            except sqlite3.DatabaseError:
                checkpoint_busy = True

            connection.execute("VACUUM")

            # 压缩后数据库已重写，再尝试截断一次 WAL，尽量把附属文件收回到最小
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            except sqlite3.DatabaseError:
                pass
            free_pages_after = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        except sqlite3.DatabaseError as exc:
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                raise RuntimeError("数据库正忙，压缩未执行，请稍后重试。") from exc
            raise RuntimeError(f"数据库压缩失败：{exc}") from exc
        finally:
            connection.close()

        size_after = os.path.getsize(database_path)
        return {
            "size_before": size_before,
            "size_after": size_after,
            "reclaimed_bytes": max(0, size_before - size_after),
            "free_pages_before": free_pages_before,
            "free_pages_after": free_pages_after,
            "checkpoint_busy": checkpoint_busy,
            "duration_seconds": round(time.perf_counter() - started_at, 2),
        }
    finally:
        _DB_VACUUM_LOCK.release()


# FastAPI依赖注入函数
def get_db(request: Request = None):
    """获取数据库会话的依赖注入函数，优先复用请求级会话。"""
    shared_db = getattr(getattr(request, "state", None), "db", None) if request is not None else None
    if shared_db is not None:
        # 会话由 add_global_context 中间件统一关闭，这里不能重复关闭。
        yield shared_db
        return

    # 在每次请求时检查配置是否变化
    db_manager.reload_if_needed()
    
    db = db_manager.get_session()
    if db:
        try:
            yield db
        finally:
            db.close()
    else:
        # 在安装向导阶段，返回None
        yield None

# 创建所有表的函数（仅用于初始设置，不用于迁移）
def create_all_tables():
    """创建所有表"""
    if db_manager.is_available:
        Base.metadata.create_all(bind=db_manager.engine)
        return True
    return False

# 兼容性别名，保持与现有代码兼容
SQLALCHEMY_DATABASE_URL = None
engine = None
SessionLocal = None

# 动态更新兼容性变量
def _update_legacy_vars():
    global SQLALCHEMY_DATABASE_URL, engine, SessionLocal
    if db_manager.is_available:
        SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
        engine = db_manager.engine
        SessionLocal = db_manager.SessionLocal

# 初始化时更新兼容性变量
_update_legacy_vars()