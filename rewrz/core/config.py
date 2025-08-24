import os
from dotenv import load_dotenv

class DynamicSettings:
    """动态配置管理器，支持运行时重新加载配置"""
    
    def __init__(self):
        self.PROJECT_NAME: str = "RewrZ"
        self._load_config()
    
    def _load_config(self):
        """加载或重新加载环境变量"""
        if os.path.exists(".env"):
            load_dotenv(override=True)  # 强制重载
        
        self.ADMIN_PATH: str = os.getenv("ADMIN_PATH", "/admin")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-default-key")
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        self.MEDIA_UPLOAD_DIR: str = os.getenv("MEDIA_UPLOAD_DIR", "media_uploads")
    
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