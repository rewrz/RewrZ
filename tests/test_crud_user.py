import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.schemas.user import UserCreate, UserUpdate
from rewrz.crud import user as crud_user
from rewrz.core.security import verify_password

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./tests/test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after tests

def test_create_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    user = crud_user.create_user(db, user_data)
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.hashed_password is not None
    assert user.role == "admin" # Default role

def test_get_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    created_user = crud_user.create_user(db, user_data)
    
    fetched_user = crud_user.get_user(db, user_id=created_user.id)
    assert fetched_user.id == created_user.id
    assert fetched_user.username == "testuser"

def test_get_user_by_username(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    crud_user.create_user(db, user_data)
    
    fetched_user = crud_user.get_user_by_username(db, username="testuser")
    assert fetched_user.username == "testuser"

def test_get_user_by_email(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    crud_user.create_user(db, user_data)
    
    fetched_user = crud_user.get_user_by_email(db, email="test@example.com")
    assert fetched_user.email == "test@example.com"

def test_update_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    created_user = crud_user.create_user(db, user_data)
    original_hashed_password = created_user.hashed_password

    update_data = UserUpdate(username="updateduser", email="updated@example.com")
    updated_user = crud_user.update_user(db, user_id=created_user.id, user_update=update_data)
    assert updated_user.username == "updateduser"
    assert updated_user.email == "updated@example.com"

    # Test updating password
    update_password_data = UserUpdate(password="newpassword")
    updated_user_password = crud_user.update_user(db, user_id=created_user.id, user_update=update_password_data)
    assert updated_user_password.hashed_password != original_hashed_password
    assert verify_password("newpassword", updated_user_password.hashed_password)

def test_delete_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    created_user = crud_user.create_user(db, user_data)

    deleted_user = crud_user.delete_user(db, user_id=created_user.id)
    assert deleted_user.id == created_user.id
    assert crud_user.get_user(db, user_id=created_user.id) is None
