from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None

class UserAvatarUpdate(BaseModel):
    """用户头像更新模型"""
    use_gravatar: Optional[str] = None
    avatar_url: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool
    avatar_url: Optional[str] = None
    avatar_filename: Optional[str] = None
    use_gravatar: bool = True
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }

class UserInDB(User):
    hashed_password: str

    model_config = {
        "from_attributes": True
    }