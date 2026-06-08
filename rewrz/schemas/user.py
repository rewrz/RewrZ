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
    theme_preference: Optional[str] = None

class UserAvatarUpdate(BaseModel):
    """用户头像更新模型"""
    use_gravatar: Optional[str] = None
    avatar_url: Optional[str] = None


class UserAdminStatusUpdate(BaseModel):
    is_active: bool


class UserAdminRoleUpdate(BaseModel):
    role: str


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=8)


class UserForceLogoutResult(BaseModel):
    token_version: int


class UserAdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=8)
    role: str = "admin"
    display_name: Optional[str] = Field(default=None, max_length=100)


class User(UserBase):
    id: int
    is_active: bool
    role: str = "admin"
    avatar_url: Optional[str] = None
    avatar_filename: Optional[str] = None
    use_gravatar: str = "auto" # 修改为str类型，默认值为"auto"
    theme_preference: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None
    token_version: int = 1

    model_config = {
        "from_attributes": True
    }

class UserInDB(User):
    hashed_password: str

    model_config = {
        "from_attributes": True
    }
