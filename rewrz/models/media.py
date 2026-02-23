from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_folder", "folder"),
        Index("ix_media_uploaded_by_folder", "uploaded_by_id", "folder"),
        Index("ix_media_file_hash", "file_hash"),
        Index("ix_media_uploaded_by_hash_size", "uploaded_by_id", "file_hash", "file_size"),
        # 优化按文件夹过滤+时间排序的分页查询
        Index("ix_media_folder_uploaded_at", "folder", "uploaded_at"),
        # 优化按上传时间排序的查询
        Index("ix_media_uploaded_at_desc", "uploaded_at"),
        # 优化按类型+时间排序的查询
        Index("ix_media_file_type_uploaded_at", "file_type", "uploaded_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, unique=True, nullable=False) # Relative path to the file
    folder = Column(String, nullable=False, default="")
    file_type = Column(String, nullable=False) # e.g., 'image', 'video', 'audio', 'document'
    mime_type = Column(String, nullable=False) # e.g., 'image/jpeg', 'video/mp4'
    file_hash = Column(String(64), nullable=False, default="")
    file_size = Column(BigInteger, nullable=False, default=0)
    title = Column(String, nullable=True)
    alt_text = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=func.now())
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))

    uploaded_by = relationship("User")
