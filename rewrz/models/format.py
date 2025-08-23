from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from .base import Base

class Format(Base):
    __tablename__ = "formats"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)

    # The relationship to Post is defined in post.py via backref
