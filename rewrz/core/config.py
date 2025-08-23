import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "RewrZ"
    ADMIN_PATH: str = os.getenv("ADMIN_PATH", "/admin") # Default admin path
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-default-key")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")  # 默认为空，避免在安装向导前创建数据库文件
    MEDIA_UPLOAD_DIR: str = os.getenv("MEDIA_UPLOAD_DIR", "media_uploads") # Directory for media uploads

settings = Settings()