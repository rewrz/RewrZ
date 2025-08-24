from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..models import Tag
from ..schemas import TagCreate, TagUpdate

def get_tag(db: Session, tag_id: int):
    return db.execute(select(Tag).filter(Tag.id == tag_id)).scalar_one_or_none()

def get_tag_by_slug(db: Session, slug: str):
    return db.execute(select(Tag).filter(Tag.slug == slug)).scalar_one_or_none()

def get_tags(db: Session, skip: int = 0, limit: int = 100):
    return db.execute(select(Tag).offset(skip).limit(limit)).scalars().all()

def get_all_tags(db: Session):
    """获取所有标签（不分页）"""
    return db.execute(select(Tag)).scalars().all()

def count_tags(db: Session) -> int:
    """
    计算所有标签的数量
    """
    return db.execute(select(func.count(Tag.id))).scalar_one()

def get_tag_by_name(db: Session, name: str):
    """根据标签名称获取标签"""
    return db.execute(select(Tag).filter(Tag.name == name)).scalar_one_or_none()

def create_tag(db: Session, tag: TagCreate):
    db_tag = Tag(name=tag.name, slug=tag.slug)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def update_tag(db: Session, tag_id: int, tag_update: TagUpdate):
    db_tag = db.execute(select(Tag).filter(Tag.id == tag_id)).scalar_one_or_none()
    if db_tag:
        for key, value in tag_update.model_dump(exclude_unset=True).items():
            setattr(db_tag, key, value)
        db.commit()
        db.refresh(db_tag)
    return db_tag

def delete_tag(db: Session, tag_id: int):
    db_tag = db.execute(select(Tag).filter(Tag.id == tag_id)).scalar_one_or_none()
    if db_tag:
        db.delete(db_tag)
        db.commit()
    return db_tag