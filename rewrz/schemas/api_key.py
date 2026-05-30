from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


API_KEY_ACCESS_LEVELS = {"read_only", "writer", "publisher", "manager"}
API_KEY_STATUSES = {"active", "disabled"}


class ApiKeyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    access_level: str = Field(default="read_only", max_length=32)
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in API_KEY_ACCESS_LEVELS:
            raise ValueError("API Key 权限等级不合法")
        return normalized


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    access_level: Optional[str] = Field(default=None, max_length=32)
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value or "").strip().lower()
        if normalized not in API_KEY_ACCESS_LEVELS:
            raise ValueError("API Key 权限等级不合法")
        return normalized


class ApiKeyStatusUpdate(BaseModel):
    status: str = Field(..., max_length=16)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in API_KEY_STATUSES:
            raise ValueError("API Key 状态不合法")
        return normalized


class ApiKeyRotateRequest(BaseModel):
    expires_at: Optional[datetime] = None


class ApiKey(ApiKeyBase):
    id: int
    key_prefix: str
    status: str
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ApiKeyCreateResult(BaseModel):
    api_key: ApiKey
    plain_token: str
