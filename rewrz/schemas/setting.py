from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SettingBase(BaseModel):
    key: str
    value: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None

class SettingCreate(SettingBase):
    pass

class SettingUpdate(BaseModel):
    value: Optional[Dict[str, Any]] = Field(default_factory=dict)
    description: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None

class Setting(SettingBase):
    id: int

    model_config = {
        "from_attributes": True
    }
