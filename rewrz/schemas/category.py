from pydantic import BaseModel
from typing import Optional

class CategoryBase(BaseModel):
    name: str
    slug: str
    parent_id: Optional[int] = None

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int

    model_config = {
        "from_attributes": True
    }

class CategoryUpdate(CategoryBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    parent_id: Optional[int] = None
