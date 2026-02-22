from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .user import User # 导入User schema

class MediaBase(BaseModel):
    filename: str
    filepath: str
    file_type: str
    mime_type: str
    title: Optional[str] = None
    alt_text: Optional[str] = None
    description: Optional[str] = None

class MediaCreate(MediaBase):
    folder: str = ""
    file_hash: str = ""
    file_size: int = 0

class MediaUpdate(BaseModel):
    title: Optional[str] = None
    alt_text: Optional[str] = None
    description: Optional[str] = None

class Media(MediaBase):
    id: int
    uploaded_at: datetime
    uploaded_by_id: int
    uploaded_by: Optional[User] = None
    url: str # 修改为str类型
    folder: Optional[str] = ""
    is_duplicate: bool = False

    model_config = {
        "from_attributes": True
    }
