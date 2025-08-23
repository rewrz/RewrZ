from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Media(Base):
    __tablename__ = "media"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, unique=True, nullable=False) # Relative path to the file
    file_type = Column(String, nullable=False) # e.g., 'image', 'video', 'audio', 'document'
    mime_type = Column(String, nullable=False) # e.g., 'image/jpeg', 'video/mp4'
    title = Column(String, nullable=True)
    alt_text = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=func.now())
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))

    uploaded_by = relationship("User")
