import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "RewrZ"
    ADMIN_PATH: str = os.getenv("ADMIN_PATH", "/admin") # Default admin path
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-default-key")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rewrz.db")
    MEDIA_UPLOAD_DIR: str = os.getenv("MEDIA_UPLOAD_DIR", "media_uploads") # Directory for media uploads

settings = Settings()
