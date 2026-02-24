import os
import secrets
from dotenv import load_dotenv


def _parse_bool_env(key: str, default: bool = False) -> bool:
    raw_value = os.getenv(key)
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
        if os.path.exists(".env"):
            load_dotenv(override=True)  # 强制重载
        
        self.ADMIN_PATH: str = str(os.getenv("ADMIN_PATH", "/admin")).strip() or "/admin"
        env_secret_key = str(os.getenv("SECRET_KEY", "")).strip()
        if _is_weak_secret_key(env_secret_key):
            self.SECRET_KEY = self._runtime_secret_key
        else:
            self.SECRET_KEY = env_secret_key
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        try:
            self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))
        except (TypeError, ValueError):
            self.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
        self.MEDIA_UPLOAD_DIR: str = os.getenv("MEDIA_UPLOAD_DIR", "media_uploads")
        self.COOKIE_SECURE: bool = _parse_bool_env("COOKIE_SECURE", False)
        self.SESSION_HTTPS_ONLY: bool = _parse_bool_env("SESSION_HTTPS_ONLY", self.COOKIE_SECURE)
    
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
        return os.path.exists(".env") and bool(self.DATABASE_URL)

settings = DynamicSettings()
