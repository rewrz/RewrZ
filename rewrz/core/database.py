from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ..models.base import Base
from .config import settings
import os

class DatabaseManager:
    """数据库连接管理器，支持动态重新初始化"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
        self.initialize()
    
    def initialize(self) -> bool:
        """初始化或重新初始化数据库连接"""
        if settings.installation_complete and settings.DATABASE_URL:
            # 清理旧连接
            if self.engine:
                self.engine.dispose()
            
            # 创建新连接
            self.engine = create_engine(
                settings.DATABASE_URL, 
                connect_args={"check_same_thread": False}
            )
            self.SessionLocal = sessionmaker(
                autocommit=False, 
                autoflush=False, 
                bind=self.engine
            )
            self._initialized = True
            return True
        return False
    
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
def get_db():
    """获取数据库会话的依赖注入函数"""
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