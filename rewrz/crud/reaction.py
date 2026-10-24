from typing import Dict, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ContentReaction


VALID_TARGET_TYPES = {"post", "comment"}
VALID_REACTION_TYPES = ("funny", "wow", "moved", "angry", "thinking", "salute")


def _normalize_target_type(target_type: str) -> str:
    normalized = (target_type or "").strip().lower()
    if normalized not in VALID_TARGET_TYPES:
        raise ValueError("invalid target_type")
    return normalized


def _normalize_target_id(target_id: int) -> int:
    try:
        value = int(target_id)
    except (TypeError, ValueError):
        raise ValueError("invalid target_id") from None
    if value <= 0:
        raise ValueError("invalid target_id")
    return value


def _normalize_reaction_type(reaction_type: Optional[str]) -> Optional[str]:
    if reaction_type is None:
        return None
    normalized = str(reaction_type).strip().lower()
    if not normalized:
        return None
    if normalized not in VALID_REACTION_TYPES:
        raise ValueError("invalid reaction_type")
    return normalized


def _ensure_record(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    visitor_token: str,
) -> ContentReaction:
    target_type = _normalize_target_type(target_type)
    target_id = _normalize_target_id(target_id)
    token = (visitor_token or "").strip()
    if not token:
        raise ValueError("invalid visitor_token")

    existing = db.execute(
        select(ContentReaction).where(
            ContentReaction.target_type == target_type,
            ContentReaction.target_id == target_id,
            ContentReaction.visitor_token == token,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    created = ContentReaction(
        target_type=target_type,
        target_id=target_id,
        visitor_token=token,
        like_active=False,
        reaction_type=None,
    )
    db.add(created)
    try:
        db.commit()
        db.refresh(created)
        return created
    except IntegrityError:
        db.rollback()
        fallback = db.execute(
            select(ContentReaction).where(
                ContentReaction.target_type == target_type,
                ContentReaction.target_id == target_id,
                ContentReaction.visitor_token == token,
            )
        ).scalar_one_or_none()
        if fallback is None:
            raise
        return fallback


def get_reaction_summary(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    visitor_token: Optional[str] = None,
) -> Dict:
    target_type = _normalize_target_type(target_type)
    target_id = _normalize_target_id(target_id)
    token = (visitor_token or "").strip()

    like_count = db.execute(
        select(func.count(ContentReaction.id)).where(
            ContentReaction.target_type == target_type,
            ContentReaction.target_id == target_id,
            ContentReaction.like_active.is_(True),
        )
    ).scalar_one()

    reaction_counts_row = db.execute(
        select(
            func.count(case((ContentReaction.reaction_type == "funny", 1))).label("funny"),
            func.count(case((ContentReaction.reaction_type == "wow", 1))).label("wow"),
            func.count(case((ContentReaction.reaction_type == "moved", 1))).label("moved"),
            func.count(case((ContentReaction.reaction_type == "angry", 1))).label("angry"),
            func.count(case((ContentReaction.reaction_type == "thinking", 1))).label("thinking"),
            func.count(case((ContentReaction.reaction_type == "salute", 1))).label("salute"),
        ).where(
            ContentReaction.target_type == target_type,
            ContentReaction.target_id == target_id,
        )
    ).one()

    reactions = {
        "funny": int(reaction_counts_row.funny or 0),
        "wow": int(reaction_counts_row.wow or 0),
        "moved": int(reaction_counts_row.moved or 0),
        "angry": int(reaction_counts_row.angry or 0),
        "thinking": int(reaction_counts_row.thinking or 0),
        "salute": int(reaction_counts_row.salute or 0),
    }

    viewer_liked = False
    viewer_reaction = None
    if token:
        viewer_record = db.execute(
            select(ContentReaction).where(
                ContentReaction.target_type == target_type,
                ContentReaction.target_id == target_id,
                ContentReaction.visitor_token == token,
            )
        ).scalar_one_or_none()
        if viewer_record is not None:
            viewer_liked = bool(viewer_record.like_active)
            viewer_reaction = viewer_record.reaction_type or None

    total_reaction_count = sum(reactions.values())
    return {
        "target_type": target_type,
        "target_id": target_id,
        "like_count": int(like_count or 0),
        "reactions": reactions,
        "total_reaction_count": total_reaction_count,
        "viewer": {
            "liked": viewer_liked,
            "reaction_type": viewer_reaction,
        },
    }


_BULK_TARGET_CHUNK_SIZE = 400


def _build_empty_summary(target_type: str, target_id: int) -> Dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "like_count": 0,
        "reactions": {reaction_type: 0 for reaction_type in VALID_REACTION_TYPES},
        "total_reaction_count": 0,
        "viewer": {"liked": False, "reaction_type": None},
    }


def get_reaction_summaries_bulk(
    db: Session,
    *,
    target_type: str,
    target_ids,
    visitor_token: Optional[str] = None,
) -> Dict[int, Dict]:
    """批量获取互动摘要，结构与 get_reaction_summary 一致。

    评论区首屏一次性取回所有评论的点赞/表情计数，避免逐条请求造成 N+1。
    """
    target_type = _normalize_target_type(target_type)

    normalized_ids = []
    for raw_id in target_ids or []:
        try:
            normalized_ids.append(_normalize_target_id(raw_id))
        except ValueError:
            continue
    normalized_ids = sorted(set(normalized_ids))
    if not normalized_ids:
        return {}

    summaries = {
        target_id: _build_empty_summary(target_type, target_id)
        for target_id in normalized_ids
    }

    for start in range(0, len(normalized_ids), _BULK_TARGET_CHUNK_SIZE):
        chunk = normalized_ids[start:start + _BULK_TARGET_CHUNK_SIZE]
        rows = db.execute(
            select(
                ContentReaction.target_id,
                func.sum(case((ContentReaction.like_active.is_(True), 1), else_=0)).label("like_count"),
                func.sum(case((ContentReaction.reaction_type == "funny", 1), else_=0)).label("funny"),
                func.sum(case((ContentReaction.reaction_type == "wow", 1), else_=0)).label("wow"),
                func.sum(case((ContentReaction.reaction_type == "moved", 1), else_=0)).label("moved"),
                func.sum(case((ContentReaction.reaction_type == "angry", 1), else_=0)).label("angry"),
                func.sum(case((ContentReaction.reaction_type == "thinking", 1), else_=0)).label("thinking"),
                func.sum(case((ContentReaction.reaction_type == "salute", 1), else_=0)).label("salute"),
            )
            .where(
                ContentReaction.target_type == target_type,
                ContentReaction.target_id.in_(chunk),
            )
            .group_by(ContentReaction.target_id)
        ).all()

        for row in rows:
            summary = summaries.get(row.target_id)
            if summary is None:
                continue
            reactions = {
                "funny": int(row.funny or 0),
                "wow": int(row.wow or 0),
                "moved": int(row.moved or 0),
                "angry": int(row.angry or 0),
                "thinking": int(row.thinking or 0),
                "salute": int(row.salute or 0),
            }
            summary["like_count"] = int(row.like_count or 0)
            summary["reactions"] = reactions
            summary["total_reaction_count"] = sum(reactions.values())

    token = (visitor_token or "").strip()
    if token:
        for start in range(0, len(normalized_ids), _BULK_TARGET_CHUNK_SIZE):
            chunk = normalized_ids[start:start + _BULK_TARGET_CHUNK_SIZE]
            viewer_records = db.execute(
                select(ContentReaction).where(
                    ContentReaction.target_type == target_type,
                    ContentReaction.target_id.in_(chunk),
                    ContentReaction.visitor_token == token,
                )
            ).scalars().all()
            for record in viewer_records:
                summary = summaries.get(record.target_id)
                if summary is None:
                    continue
                summary["viewer"] = {
                    "liked": bool(record.like_active),
                    "reaction_type": record.reaction_type or None,
                }

    return summaries


def set_like_state(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    visitor_token: str,
    like_active: Optional[bool] = None,
) -> Tuple[bool, Dict]:
    record = _ensure_record(
        db,
        target_type=target_type,
        target_id=target_id,
        visitor_token=visitor_token,
    )

    if like_active is None:
        record.like_active = not bool(record.like_active)
    else:
        record.like_active = bool(like_active)

    db.add(record)
    db.commit()
    db.refresh(record)

    summary = get_reaction_summary(
        db,
        target_type=target_type,
        target_id=target_id,
        visitor_token=visitor_token,
    )
    return bool(record.like_active), summary


def set_reaction_state(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    visitor_token: str,
    reaction_type: Optional[str],
) -> Tuple[Optional[str], Dict]:
    record = _ensure_record(
        db,
        target_type=target_type,
        target_id=target_id,
        visitor_token=visitor_token,
    )

    normalized = _normalize_reaction_type(reaction_type)
    if normalized == (record.reaction_type or None):
        record.reaction_type = None
    else:
        record.reaction_type = normalized

    db.add(record)
    db.commit()
    db.refresh(record)

    summary = get_reaction_summary(
        db,
        target_type=target_type,
        target_id=target_id,
        visitor_token=visitor_token,
    )
    return record.reaction_type or None, summary
