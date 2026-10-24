import unicodedata
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from slugify import slugify

from ..models import Tag
from ..models.post import post_tags
from ..schemas import TagCreate, TagUpdate


def normalize_tag_text(value: str) -> str:
    """标签输入统一做去空白与 Unicode NFC 归一化。"""
    return unicodedata.normalize("NFC", str(value or "").strip())


def normalize_tag_key(value: str) -> str:
    """用于名称/slug 匹配的比较键：NFC + 去空白 + 大小写折叠。"""
    return normalize_tag_text(value).casefold()


def find_tag_by_name_or_slug(db: Session, raw_value: str) -> Optional[Tag]:
    """按标签名称或 slug 查找标签，兼容大小写、空白与 Unicode 差异。

    查找优先级：名称 > slug，避免同名的标签被 slug 误匹配到其他标签。
    """
    normalized = normalize_tag_text(raw_value)
    if not normalized:
        return None

    lookup_key = normalized.casefold()
    tag = db.execute(select(Tag).where(Tag.name == normalized)).scalars().first()
    if tag is not None:
        return tag
    tag = db.execute(select(Tag).where(func.lower(Tag.name) == lookup_key)).scalars().first()
    if tag is not None:
        return tag
    tag = db.execute(select(Tag).where(Tag.slug == normalized)).scalars().first()
    if tag is not None:
        return tag
    tag = db.execute(select(Tag).where(func.lower(Tag.slug) == lookup_key)).scalars().first()
    if tag is not None:
        return tag

    # SQL 的 lower() 无法覆盖全部 Unicode 情况，最后在 Python 侧兜底。
    for candidate in db.execute(select(Tag)).scalars():
        if normalize_tag_key(candidate.name) == lookup_key or normalize_tag_key(candidate.slug) == lookup_key:
            return candidate
    return None


def find_conflicting_tag(
    db: Session,
    *,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    exclude_tag_id: Optional[int] = None,
) -> Optional[Tag]:
    """后台创建/编辑标签时检查名称与 slug 是否已被占用。"""
    name_key = normalize_tag_key(name) if name else ""
    slug_key = normalize_tag_key(slug) if slug else ""
    for candidate in db.execute(select(Tag)).scalars():
        if exclude_tag_id is not None and candidate.id == exclude_tag_id:
            continue
        candidate_name_key = normalize_tag_key(candidate.name)
        candidate_slug_key = normalize_tag_key(candidate.slug)
        if name_key and (candidate_name_key == name_key or candidate_slug_key == name_key):
            return candidate
        if slug_key and (candidate_slug_key == slug_key or candidate_name_key == slug_key):
            return candidate
    return None


def resolve_or_create_tag(db: Session, raw_name: str, *, create_if_missing: bool = True) -> Optional[Tag]:
    """把用户输入的标签名称/slug 解析为已有标签，不存在时再创建。"""
    normalized_name = normalize_tag_text(raw_name)
    if not normalized_name:
        return None

    tag = find_tag_by_name_or_slug(db, normalized_name)
    if tag is not None:
        return tag
    if not create_if_missing:
        return None

    base_slug = slugify(normalized_name) or "tag"
    # 用户也可能直接写 slug；slug 已被占用时复用已有标签，避免重复与唯一约束报错。
    tag = db.execute(select(Tag).where(Tag.slug == base_slug)).scalars().first()
    if tag is not None:
        return tag

    tag = Tag(name=normalized_name, slug=base_slug)
    try:
        # 并发发布时可能被其他请求抢先创建；用保存点避免污染整篇文章事务。
        with db.begin_nested():
            db.add(tag)
            db.flush()
    except IntegrityError:
        if tag in db:
            db.expunge(tag)
        tag = find_tag_by_name_or_slug(db, normalized_name)
        if tag is None:
            tag = db.execute(select(Tag).where(Tag.slug == base_slug)).scalars().first()
        if tag is None:
            raise
    return tag


def resolve_or_create_tags(
    db: Session,
    raw_names: Optional[List[str]],
    *,
    limit: Optional[int] = None,
) -> List[Tag]:
    """批量解析标签，按解析后的标签 ID 去重，并可选限制数量。"""
    resolved: List[Tag] = []
    seen_ids = set()
    for raw_name in raw_names or []:
        tag = resolve_or_create_tag(db, raw_name)
        if tag is None or tag.id in seen_ids:
            continue
        seen_ids.add(tag.id)
        resolved.append(tag)
        if limit is not None and len(resolved) >= limit:
            break
    return resolved


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
