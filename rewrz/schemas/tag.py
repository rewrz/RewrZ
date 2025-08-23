from pydantic import BaseModel
from typing import Optional

class TagBase(BaseModel):
    name: str
    slug: str

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
