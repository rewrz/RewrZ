import os
import threading

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