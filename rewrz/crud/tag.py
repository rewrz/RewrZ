import math
import unicodedata
from difflib import SequenceMatcher
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


_SUGGEST_MIN_SCORE = 35.0
_SUGGEST_MATCH_LIMIT = 20


def _char_overlap_ratio(left: str, right: str) -> float:
    """字符集合重合度，对中文短标签比编辑距离更宽容。"""
    left_chars = set(left)
    right_chars = set(right)
    if not left_chars or not right_chars:
        return 0.0
    return len(left_chars & right_chars) / len(left_chars | right_chars)


def _score_tag_candidate(query_key: str, name_key: str) -> tuple[float, str]:
    """给候选标签打分，同时返回命中类型供前端展示。"""
    if name_key == query_key:
        return 100.0, "exact"
    if name_key.startswith(query_key):
        return 92.0, "prefix"
    if query_key in name_key:
        return 84.0, "contains"
    if name_key in query_key:
        return 76.0, "contains"
    ratio = SequenceMatcher(None, query_key, name_key).ratio()
    overlap = _char_overlap_ratio(query_key, name_key)
    score = round(max(ratio, overlap * 0.92) * 74.0, 2)
    return score, "similar"


def _load_post_counts(db: Session, tag_ids: List[int]) -> dict[int, int]:
    if not tag_ids:
        return {}
    counts: dict[int, int] = {}
    for offset in range(0, len(tag_ids), 300):
        batch = tag_ids[offset : offset + 300]
        rows = db.execute(
            select(post_tags.c.tag_id, func.count(post_tags.c.post_id))
            .where(post_tags.c.tag_id.in_(batch))
            .group_by(post_tags.c.tag_id)
        ).all()
        for tag_id, count in rows:
            try:
                counts[int(tag_id)] = int(count or 0)
            except (TypeError, ValueError):
                continue
    return counts


def suggest_tags(
    db: Session,
    query: str,
    *,
    limit: int = 8,
    exclude: Optional[List[str]] = None,
) -> List[dict]:
    """按输入推荐已有标签，避免用户把近义标签拆成多个。

    返回按匹配度排序的候选：精确命中最高，其次是前缀、包含、相似；
    使用量只作为同分时的次要权重，防止长尾高频标签盖过明显的文本匹配。
    """
    limit = max(1, min(int(limit or 8), _SUGGEST_MATCH_LIMIT))
    exclude_keys = {
        normalize_tag_key(item) for item in (exclude or []) if normalize_tag_key(item)
    }
    query_key = normalize_tag_key(query)

    if not query_key:
        # 空输入展示常用标签，方便直接点选已有标签而不是新建
        rows = db.execute(
            select(Tag.id, Tag.name, Tag.slug, func.count(post_tags.c.post_id))
            .outerjoin(post_tags, post_tags.c.tag_id == Tag.id)
            .group_by(Tag.id, Tag.name, Tag.slug)
            .order_by(func.count(post_tags.c.post_id).desc(), Tag.name.asc())
            .limit(limit + len(exclude_keys) + 5)
        ).all()
        items = []
        for tag_id, name, slug, count in rows:
            if normalize_tag_key(name) in exclude_keys:
                continue
            items.append(
                {
                    "id": int(tag_id),
                    "name": name,
                    "slug": slug,
                    "post_count": int(count or 0),
                    "score": 0.0,
                    "match": "popular",
                }
            )
            if len(items) >= limit:
                break
        return items

    rows = db.execute(select(Tag.id, Tag.name, Tag.slug)).all()
    scored: list[tuple[float, str, int, str, str]] = []
    for tag_id, name, slug in rows:
        name_key = normalize_tag_key(name)
        if not name_key or name_key in exclude_keys:
            continue
        score, match = _score_tag_candidate(query_key, name_key)
        if score < _SUGGEST_MIN_SCORE:
            continue
        scored.append((score, match, int(tag_id), name, slug))

    if not scored:
        return []

    scored.sort(key=lambda item: (-item[0], item[3]))
    count_map = _load_post_counts(db, [item[2] for item in scored[: limit * 2]])

    items = []
    for score, match, tag_id, name, slug in scored[: limit * 2]:
        post_count = int(count_map.get(tag_id, 0))
        # 使用量最多加 6 分，只用于同分附近的排序，不改变命中类型的优先级
        weighted = round(score + min(6.0, math.log2(1 + post_count) * 1.2), 2)
        items.append(
            {
                "id": tag_id,
                "name": name,
                "slug": slug,
                "post_count": post_count,
                "score": weighted,
                "match": match,
            }
        )
    items.sort(key=lambda item: (-item["score"], -item["post_count"], item["name"]))
    return items[:limit]


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
    db_tag = Tag(name=tag.name, slug=tag.slug, description=tag.description or "")
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
