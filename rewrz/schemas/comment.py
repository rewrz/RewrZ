from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

class CommentBase(BaseModel):
    post_id: int
    parent_id: Optional[int] = None
    author_name: str
    author_email: str
    author_url: Optional[HttpUrl] = None
    content: str

class CommentCreate(CommentBase):
    status: str = "pending"

class Comment(CommentBase):
    id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: str = "pending"
    is_admin_reply: bool = False
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
