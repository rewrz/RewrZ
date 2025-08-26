from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime
from .category import Category
from .tag import Tag
from .format import Format # Import Format schema

class PostBase(BaseModel):
    title: str
    slug: Optional[str] = None
    content_markdown: str
    excerpt: Optional[str] = None
    featured_image_url: Optional[HttpUrl] = None
    post_type: str = "post"
    status: str = "draft"
    visibility: str = "public"
    password: Optional[str] = None
    allow_comments: bool = True
    license_type: Optional[str] = "cc_by_nc_sa_4"  # 版权协议类型
    version_snapshots: List[dict] = Field(default_factory=list)

class PostCreate(PostBase):
    category_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    format_ids: Optional[List[int]] = None

class PostUpdate(PostBase):
    title: Optional[str] = None
    slug: Optional[str] = None
    content_markdown: Optional[str] = None
    category_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    format_ids: Optional[List[int]] = None
    license_type: Optional[str] = None  # 版权协议更新

class Post(PostBase):
    id: int
    content_html: str
    created_at: datetime
    published_at: Optional[datetime] = None
    updated_at: datetime
    author_id: int
    categories: List[Category] = [] # Add categories
    tags: List[Tag] = [] # Add tags
    formats: List[Format] = [] # Add formats

    model_config = {
        "from_attributes": True
    }
