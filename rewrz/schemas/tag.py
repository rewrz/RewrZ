from pydantic import BaseModel
from typing import Optional

class TagBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class TagCreate(TagBase):
    pass

class Tag(TagBase):
    id: int

    model_config = {
        "from_attributes": True
    }

class TagUpdate(TagBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
