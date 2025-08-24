from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models import Media
from ..schemas import MediaCreate, MediaUpdate
from typing import List

def get_media(db: Session, media_id: int):
    return db.execute(select(Media).filter(Media.id == media_id)).scalar_one_or_none()

def get_media_by_filepath(db: Session, filepath: str):
    return db.execute(select(Media).filter(Media.filepath == filepath)).scalar_one_or_none()

def get_all_media_items(db: Session, skip: int = 0, limit: int = 100) -> List[Media]:
    """
    获取所有媒体项目

    Args:
        db (Session): 数据库会话.
        skip (int, optional): 跳过的项目数. Defaults to 0.
        limit (int, optional): 返回的最大项目数. Defaults to 100.

    Returns:
        List[Media]: 媒体项目列表.
    """
    return db.execute(select(Media).offset(skip).limit(limit)).scalars().all()

def create_media(db: Session, media: MediaCreate, uploaded_by_id: int):
    db_media = Media(
        filename=media.filename,
        filepath=media.filepath,
        file_type=media.file_type,
        mime_type=media.mime_type,
        title=media.title,
        alt_text=media.alt_text,
        description=media.description,
        uploaded_by_id=uploaded_by_id
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

def update_media(db: Session, media_id: int, media_update: MediaUpdate):
    db_media = db.execute(select(Media).filter(Media.id == media_id)).scalar_one_or_none()
    if db_media:
        for key, value in media_update.model_dump(exclude_unset=True).items():
            setattr(db_media, key, value)
        db.commit()
        db.refresh(db_media)
    return db_media

def delete_media(db: Session, media_id: int):
    db_media = db.execute(select(Media).filter(Media.id == media_id)).scalar_one_or_none()
    if db_media:
        db.delete(db_media)
        db.commit()
    return db_media
