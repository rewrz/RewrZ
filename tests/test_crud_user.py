from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rewrz.crud import user as crud_user
from rewrz.core.database import Base
from rewrz.core.security import verify_password
from rewrz.schemas.user import UserCreate, UserUpdate


@pytest.fixture(name="db")
def session_fixture(tmp_path):
    db_path = tmp_path / f"crud-user-{uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_create_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    user = crud_user.create_user(db, user_data)
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.hashed_password is not None
    assert user.role == "admin"


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


def test_get_users_supports_search(db: Session):
    crud_user.create_user(db, UserCreate(username="alpha", email="alpha@example.com", password="testpassword"))
    crud_user.create_user(db, UserCreate(username="beta", email="beta@example.com", password="testpassword"))

    all_users = crud_user.get_users(db)
    assert len(all_users) >= 2

    matched = crud_user.get_users(db, search="alpha")
    assert len(matched) == 1
    assert matched[0].username == "alpha"


def test_update_user(db: Session):
    user_data = UserCreate(username="testuser", email="test@example.com", password="testpassword")
    created_user = crud_user.create_user(db, user_data)
    original_hashed_password = created_user.hashed_password

    update_data = UserUpdate(username="updateduser", email="updated@example.com")
    updated_user = crud_user.update_user(db, user_id=created_user.id, user_update=update_data)
    assert updated_user.username == "updateduser"
    assert updated_user.email == "updated@example.com"

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


def test_set_user_active_status(db: Session):
    created_user = crud_user.create_user(
        db,
        UserCreate(username="statususer", email="status@example.com", password="testpassword"),
    )
    updated_user = crud_user.set_user_active_status(db, created_user.id, is_active=False)
    assert updated_user.is_active is False


def test_set_user_role(db: Session):
    created_user = crud_user.create_user(
        db,
        UserCreate(username="roleuser", email="role@example.com", password="testpassword"),
    )
    updated_user = crud_user.set_user_role(db, created_user.id, role="super_admin")
    assert updated_user.role == "super_admin"


def test_reset_user_password(db: Session):
    created_user = crud_user.create_user(
        db,
        UserCreate(username="resetuser", email="reset@example.com", password="oldpassword"),
    )
    original_hash = created_user.hashed_password
    updated_user = crud_user.reset_user_password(db, created_user.id, password="newpassword123")
    assert updated_user.hashed_password != original_hash
    assert verify_password("newpassword123", updated_user.hashed_password)
