from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, select
from ..models import Media
from ..schemas import MediaCreate, MediaUpdate
from typing import List, Optional

def get_media(db: Session, media_id: int):
    return db.execute(select(Media).filter(Media.id == media_id)).scalar_one_or_none()

def get_media_by_filepath(db: Session, filepath: str):
    return db.execute(select(Media).filter(Media.filepath == filepath)).scalar_one_or_none()

def get_all_media(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    folder: Optional[str] = None,
    file_type_prefix: Optional[str] = None,
    uploaded_from: Optional[datetime] = None,
    uploaded_to: Optional[datetime] = None,
) -> List[Media]:
    """
    获取所有媒体项目，按上传时间降序排列（最新的在前面）

    Args:
        db (Session): 数据库会话.
        skip (int, optional): 跳过的项目数. Defaults to 0.
        limit (int, optional): 返回的最大项目数. Defaults to 100.
        search (str, optional): 搜索关键词，用于模糊匹配文件名或标题. Defaults to None.
        folder (str, optional): 文件夹路径（精确匹配）. Defaults to None.
        file_type_prefix (str, optional): 媒体类型前缀过滤（如 image/video/audio）. Defaults to None.
        uploaded_from (datetime, optional): 上传时间起始（含）. Defaults to None.
        uploaded_to (datetime, optional): 上传时间结束（含）. Defaults to None.

    Returns:
        List[Media]: 媒体项目列表，按上传时间降序排列.
    """
    query = select(Media).order_by(desc(Media.uploaded_at))
    if search:
        query = query.filter(Media.filename.ilike(f"%{search}%") | Media.title.ilike(f"%{search}%"))
    if folder is not None:
        query = query.filter(Media.folder == folder)
    if file_type_prefix:
        query = query.filter(Media.file_type.ilike(f"{file_type_prefix}%"))
    if uploaded_from is not None:
        query = query.filter(Media.uploaded_at >= uploaded_from)
    if uploaded_to is not None:
        query = query.filter(Media.uploaded_at <= uploaded_to)
    
    return db.execute(query.offset(skip).limit(limit)).scalars().all()


def get_media_ids(
    db: Session,
    *,
    search: Optional[str] = None,
    folder: Optional[str] = None,
    file_type_prefix: Optional[str] = None,
    uploaded_from: Optional[datetime] = None,
    uploaded_to: Optional[datetime] = None,
    limit: int = 10000,
) -> List[int]:
    query = select(Media.id).order_by(desc(Media.uploaded_at))
    if search:
        query = query.filter(Media.filename.ilike(f"%{search}%") | Media.title.ilike(f"%{search}%"))
    if folder is not None:
        query = query.filter(Media.folder == folder)
    if file_type_prefix:
        query = query.filter(Media.file_type.ilike(f"{file_type_prefix}%"))
    if uploaded_from is not None:
        query = query.filter(Media.uploaded_at >= uploaded_from)
    if uploaded_to is not None:
        query = query.filter(Media.uploaded_at <= uploaded_to)

    effective_limit = max(1, min(int(limit), 20000))
    return [int(media_id) for media_id in db.execute(query.limit(effective_limit)).scalars().all()]

def create_media(db: Session, media: MediaCreate, uploaded_by_id: int):
    db_media = Media(
        filename=media.filename,
        filepath=media.filepath,
        folder=media.folder,
        file_type=media.file_type,
        mime_type=media.mime_type,
        file_hash=media.file_hash,
        file_size=media.file_size,
        title=media.title,
        alt_text=media.alt_text,
        description=media.description,
        uploaded_by_id=uploaded_by_id
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media


def get_media_by_hash_and_size(
    db: Session,
    file_hash: str,
    file_size: int,
) -> Optional[Media]:
    return db.execute(
        select(Media)
        .filter(Media.file_hash == file_hash)
        .filter(Media.file_size == int(file_size))
        .order_by(Media.id.asc())
    ).scalars().first()

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
