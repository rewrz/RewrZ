from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ..models.base import Base
from .config import settings
import os

# SQLite database URL
# 只有在.env文件存在时才创建引擎，避免安装向导前创建数据库文件
if os.path.exists(".env"):
    SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
    # Create the SQLAlchemy engine
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    
    # Create a SessionLocal class
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    SQLALCHEMY_DATABASE_URL = None
    engine = None
    SessionLocal = None

# Dependency to get the database session
def get_db():
    # 只有在SessionLocal存在时才创建数据库会话
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    else:
        # 在安装向导阶段，返回None
        yield None

# Function to create all tables (for initial setup, not for migrations)
def create_all_tables():
    # 只有在engine存在时才创建表
    if engine is not None:
        Base.metadata.create_all(bind=engine)