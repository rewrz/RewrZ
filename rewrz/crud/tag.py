from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..models import Tag
from ..models.post import post_tags
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


def bulk_delete_tags(db: Session, tag_ids: list[int]):
    """批量删除标签（单事务提交），并返回可用于前端提示的删除结果。"""
    if not tag_ids:
        return {
            "deleted_ids": [],
            "missing_ids": [],
            "blocked_by_posts_ids": [],
        }

    existing_ids = set(
        db.execute(select(Tag.id).filter(Tag.id.in_(tag_ids))).scalars().all()
    )
    if not existing_ids:
        return {
            "deleted_ids": [],
            "missing_ids": tag_ids,
            "blocked_by_posts_ids": [],
        }

    blocked_by_posts_ids = set(
        db.execute(
            select(post_tags.c.tag_id)
            .filter(post_tags.c.tag_id.in_(existing_ids))
            .distinct()
        ).scalars().all()
    )
    deletable_ids = [tag_id for tag_id in tag_ids if tag_id in existing_ids and tag_id not in blocked_by_posts_ids]

    if deletable_ids:
        db.query(Tag).filter(Tag.id.in_(deletable_ids)).delete(synchronize_session=False)
        db.commit()

    missing_ids = [tag_id for tag_id in tag_ids if tag_id not in existing_ids]
    return {
        "deleted_ids": deletable_ids,
        "missing_ids": missing_ids,
        "blocked_by_posts_ids": [tag_id for tag_id in tag_ids if tag_id in blocked_by_posts_ids],
    }
