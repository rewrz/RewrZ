import os
import secrets
from dotenv import dotenv_values


def get_env_file_path() -> str:
    raw_path = str(os.getenv("REWRZ_ENV_FILE", ".env")).strip()
    return raw_path or ".env"


def _parse_bool_value(raw_value, default: bool = False) -> bool:
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


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
        self._load_config()
    
    def _load_config(self):
        """加载或重新加载环境变量"""
        env_file_path = get_env_file_path()
        file_env = {}
        if os.path.exists(env_file_path):
            file_env = {
                key: "" if value is None else str(value)
                for key, value in dotenv_values(env_file_path).items()
            }

        def get_value(key: str, default=""):
            if key in file_env:
                return file_env[key]
            return os.getenv(key, default)
        
        self.ADMIN_PATH: str = str(get_value("ADMIN_PATH", "/admin")).strip() or "/admin"
        env_secret_key = str(get_value("SECRET_KEY", "")).strip()
        if _is_weak_secret_key(env_secret_key):
            self.SECRET_KEY = self._runtime_secret_key
        else:
            self.SECRET_KEY = env_secret_key
        self.DATABASE_URL: str = str(get_value("DATABASE_URL", "")).strip()
        try:
            self.ACCESS_TOKEN_EXPIRE_MINUTES = int(get_value("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))
        except (TypeError, ValueError):
            self.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
        self.MEDIA_UPLOAD_DIR: str = str(get_value("MEDIA_UPLOAD_DIR", "media_uploads")).strip() or "media_uploads"
        self.COOKIE_SECURE: bool = _parse_bool_value(get_value("COOKIE_SECURE"), False)
        self.SESSION_HTTPS_ONLY: bool = _parse_bool_value(
            get_value("SESSION_HTTPS_ONLY"),
            self.COOKIE_SECURE,
        )
    
    def reload_config(self) -> bool:
        """重新加载配置，返回是否有变化"""
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
