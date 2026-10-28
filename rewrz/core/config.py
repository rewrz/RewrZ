import os
import secrets
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

DEFAULT_SITE_TIMEZONE = "Asia/Shanghai"


def get_env_file_path() -> str:
    raw_path = str(os.getenv("REWRZ_ENV_FILE", ".env")).strip()
    return raw_path or ".env"


def _read_env_file_mtime(path: str) -> float | None:
    """读取 .env 的修改时间；文件不存在或读取失败时返回 None。"""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _parse_bool_value(raw_value, default: bool = False) -> bool:
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_value(raw_value, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _is_weak_secret_key(secret_key: str) -> bool:
    weak_values = {
        "",
        "super-secret-default-key",
        "super-secret-default-key-change-in-production",
        "change-me",
        "please-change-me",
    }
    return str(secret_key or "").strip() in weak_values


class DynamicSettings:
    """动态配置管理器，支持运行时重新加载配置"""
    
    def __init__(self):
        self.PROJECT_NAME: str = "RewrZ"
        self._runtime_secret_key: str = secrets.token_urlsafe(48)
        self._env_file_mtime: float | None = None
        self._load_config()
    
    def _load_config(self):
        """加载或重新加载环境变量"""
        env_file_path = get_env_file_path()
        env_file_mtime = _read_env_file_mtime(env_file_path)
        file_env = {}
        if os.path.exists(env_file_path):
            file_env = {
                key: "" if value is None else str(value)
                for key, value in dotenv_values(env_file_path).items()
            }

        def get_value(key: str, default=""):
            # 进程环境变量优先，便于测试与部署覆盖 .env
            env_value = os.getenv(key)
            if env_value is not None:
                return env_value
            if key in file_env:
                return file_env[key]
            return default
        
        self.ADMIN_PATH: str = str(get_value("ADMIN_PATH", "/admin")).strip() or "/admin"
        env_secret_key = str(get_value("SECRET_KEY", "")).strip()
        if _is_weak_secret_key(env_secret_key):
            self.SECRET_KEY = self._runtime_secret_key
        else:
            self.SECRET_KEY = env_secret_key
        self.DATABASE_URL: str = str(get_value("DATABASE_URL", "")).strip()
        # SQLite 在 WAL 下读可并发、写串行：池大小主要决定同时能有多少个读查询。
        # 默认 16+8 与 uvicorn 的并发上限配合，既避免池被瞬间打满，
        # 也不会让空闲连接把内存拖高（每连接页缓存由 SQLITE_CACHE_SIZE_KIB 限死）。
        # 网络数据库仍保留 10+20 的默认并发能力。
        is_sqlite_database = self.DATABASE_URL.lower().startswith("sqlite")
        default_pool_size = 16 if is_sqlite_database else 10
        default_max_overflow = 8 if is_sqlite_database else 20
        self.DB_POOL_SIZE: int = _parse_int_value(
            get_value("DB_POOL_SIZE", default_pool_size),
            default_pool_size,
            minimum=1,
            maximum=100,
        )
        self.DB_MAX_OVERFLOW: int = _parse_int_value(
            get_value("DB_MAX_OVERFLOW", default_max_overflow),
            default_max_overflow,
            minimum=0,
            maximum=200,
        )
        # 池等待必须快速失败：请求会在有界线程池里等待，不再阻塞事件循环
        self.DB_POOL_TIMEOUT: int = _parse_int_value(get_value("DB_POOL_TIMEOUT", 3), 3, minimum=1, maximum=60)
        self.DB_POOL_RECYCLE: int = _parse_int_value(get_value("DB_POOL_RECYCLE", 1800), 1800, minimum=0, maximum=86400)
        self.DB_POOL_PRE_PING: bool = _parse_bool_value(get_value("DB_POOL_PRE_PING"), True)
        # 写锁等待上限：默认 5 秒。20 个连接 × 30 秒会把整池按分钟级锁死，必须收敛。
        self.SQLITE_BUSY_TIMEOUT_MS: int = _parse_int_value(
            get_value("SQLITE_BUSY_TIMEOUT_MS", 5000), 5000, minimum=1000, maximum=60000
        )
        # 慢 SQL 与连接长期持有的告警阈值，用于定位卡点
        self.SLOW_SQL_LOG_MS: int = _parse_int_value(
            get_value("SLOW_SQL_LOG_MS", 500), 500, minimum=50, maximum=60000
        )
        self.DB_HOLD_WARN_MS: int = _parse_int_value(
            get_value("DB_HOLD_WARN_MS", 3000), 3000, minimum=100, maximum=600000
        )
        self.SQLITE_JOURNAL_MODE: str = str(get_value("SQLITE_JOURNAL_MODE", "WAL")).strip().upper() or "WAL"
        # 每个 SQLite 连接的页缓存上限（KiB）。默认 1MB，24 个连接最坏约 24MB；
        # 比 SQLite 默认的 2MB/连接更省内存，同时保留读并发。
        self.SQLITE_CACHE_SIZE_KIB: int = _parse_int_value(
            get_value("SQLITE_CACHE_SIZE_KIB", 1024), 1024, minimum=256, maximum=8192
        )
        # WAL 下 synchronous=NORMAL 可大幅减少每次提交的 fsync，
        # 断电时可能丢失最后少量事务，对博客场景可接受。
        self.SQLITE_SYNCHRONOUS: str = str(get_value("SQLITE_SYNCHRONOUS", "NORMAL")).strip().upper() or "NORMAL"
        # 站点对外地址，用于生成邮件链接等，避免依赖请求 Host 头
        self.SITE_URL: str = str(get_value("SITE_URL", "")).strip().rstrip("/")
        # 允许的 Host 头白名单（逗号分隔，为空表示不启用校验）
        self.ALLOWED_HOSTS: list[str] = [
            item.strip().lower()
            for item in str(get_value("ALLOWED_HOSTS", "")).split(",")
            if item.strip()
        ]
        # 可信反向代理地址/CIDR（逗号分隔），用于解析 X-Forwarded-For
        self.TRUSTED_PROXIES: list[str] = [
            item.strip()
            for item in str(get_value("TRUSTED_PROXIES", "127.0.0.1,::1")).split(",")
            if item.strip()
        ]
        # 站点展示时区（IANA 名称），数据库统一存 UTC，渲染时按该时区转换
        raw_site_timezone = str(get_value("SITE_TIMEZONE", DEFAULT_SITE_TIMEZONE)).strip() or DEFAULT_SITE_TIMEZONE
        try:
            ZoneInfo(raw_site_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raw_site_timezone = DEFAULT_SITE_TIMEZONE
        self.SITE_TIMEZONE: str = raw_site_timezone
        self.ACCESS_TOKEN_EXPIRE_MINUTES = _parse_int_value(
            get_value("ACCESS_TOKEN_EXPIRE_MINUTES", 1440),
            1440,
            minimum=5,
            maximum=10080,
        )
        self.MEDIA_UPLOAD_DIR: str = str(get_value("MEDIA_UPLOAD_DIR", "media_uploads")).strip() or "media_uploads"
        # 垃圾爬虫与扫描路径拦截开关：默认开启，正规搜索引擎与监控 UA 不受影响
        self.BOT_BLOCK_ENABLED: bool = _parse_bool_value(get_value("BOT_BLOCK_ENABLED", "true"), True)
        # 可选强制开关：默认不写，Cookie Secure 标志由 should_use_secure_cookie 按请求自动判定
        self.COOKIE_SECURE: bool = _parse_bool_value(get_value("COOKIE_SECURE"), False)
        self._env_file_mtime = env_file_mtime
    
    def reload_config(self, force: bool = False) -> bool:
        """重新加载配置，返回是否有变化。

        默认按 .env 的修改时间判断：未变化时只做一次 stat，不再解析整个文件。
        安装向导等明确需要重读的场景传 force=True。
        """
        if not force:
            current_mtime = _read_env_file_mtime(get_env_file_path())
            if current_mtime == self._env_file_mtime:
                return False

        old_db_url = getattr(self, 'DATABASE_URL', '')
        old_admin_path = getattr(self, 'ADMIN_PATH', '/admin')
        
        self._load_config()
        
        return (old_db_url != self.DATABASE_URL or 
                old_admin_path != self.ADMIN_PATH)
    
    @property
    def installation_complete(self) -> bool:
        """检查安装是否完成"""
        return os.path.exists(get_env_file_path()) and bool(self.DATABASE_URL)

settings = DynamicSettings()
