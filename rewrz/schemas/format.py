from pydantic import BaseModel
from typing import Optional

class FormatBase(BaseModel):
    name: str
    slug: str

class FormatCreate(FormatBase):
    pass

class FormatUpdate(FormatBase):
    name: Optional[str] = None
    slug: Optional[str] = None

class Format(FormatBase):
    id: int

    model_config = {
        "from_attributes": True
    }
