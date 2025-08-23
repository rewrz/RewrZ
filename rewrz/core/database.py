from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ..models.base import Base
from .config import settings

# SQLite database URL
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Create the SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to create all tables (for initial setup, not for migrations)
def create_all_tables():
    Base.metadata.create_all(bind=engine)
