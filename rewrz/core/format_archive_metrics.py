"""格式归档页聚合统计辅助逻辑。"""

from typing import Any, Dict, List, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.comment import Comment
from ..models.post import Post, post_categories, post_tags
from ..models.reaction import ContentReaction
from ..models.tag import Tag


def attach_format_comment_counts(db: Session, posts: Sequence[Post]) -> None:
    """为格式归档列表附加评论计数。"""
    post_ids = [item.id for item in posts if getattr(item, "id", None) is not None]
    if not post_ids:
        return

    comment_rows = db.execute(
        select(Comment.post_id, func.count(Comment.id))
        .where(Comment.post_id.in_(post_ids), Comment.status == "approved")
        .group_by(Comment.post_id)
    ).all()
    comment_count_map = {int(post_id): int(count or 0) for post_id, count in comment_rows}
    for item in posts:
        setattr(item, "comment_count", int(comment_count_map.get(item.id, 0)))


def build_micro_interaction_count(db: Session, format_post_ids_query) -> int:
    """统计微博格式的总互动数。"""
    micro_comment_total = db.execute(
        select(func.count(Comment.id)).where(
            Comment.status == "approved",
            Comment.post_id.in_(format_post_ids_query),
        )
    ).scalar_one()
    micro_like_total = db.execute(
        select(func.count(ContentReaction.id)).where(
            ContentReaction.target_type == "post",
            ContentReaction.target_id.in_(format_post_ids_query),
            ContentReaction.like_active.is_(True),
        )
    ).scalar_one()
    micro_reaction_total = db.execute(
        select(func.count(ContentReaction.id)).where(
            ContentReaction.target_type == "post",
            ContentReaction.target_id.in_(format_post_ids_query),
            ContentReaction.reaction_type.isnot(None),
        )
    ).scalar_one()

    return int(
        (micro_comment_total or 0)
        + (micro_like_total or 0)
        + (micro_reaction_total or 0)
    )


def build_format_tag_metrics(
    db: Session,
    *,
    format_post_ids_query,
    load_post_views_metrics_map,
) -> tuple[int, List[Dict[str, Any]]]:
    """统计标签主题数与热门标签列表。"""
    tag_post_rows = db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.slug,
            post_tags.c.post_id,
        )
        .join(post_tags, post_tags.c.tag_id == Tag.id)
        .where(post_tags.c.post_id.in_(format_post_ids_query))
    ).all()

    format_tag_topic_count = len(
        {int(row.id) for row in tag_post_rows if getattr(row, "id", None) is not None}
    )
    if not tag_post_rows:
        return format_tag_topic_count, []

    tagged_post_ids_query = (
        select(post_tags.c.post_id)
        .where(post_tags.c.post_id.in_(format_post_ids_query))
        .group_by(post_tags.c.post_id)
    )
    tagged_post_ids = sorted(
        {
            int(row.post_id)
            for row in tag_post_rows
            if getattr(row, "post_id", None) is not None
        }
    )

    tag_comment_rows = db.execute(
        select(Comment.post_id, func.count(Comment.id))
        .where(
            Comment.status == "approved",
            Comment.post_id.in_(tagged_post_ids_query),
        )
        .group_by(Comment.post_id)
    ).all()
    tag_like_rows = db.execute(
        select(ContentReaction.target_id, func.count(ContentReaction.id))
        .where(
            ContentReaction.target_type == "post",
            ContentReaction.target_id.in_(tagged_post_ids_query),
            ContentReaction.like_active.is_(True),
        )
        .group_by(ContentReaction.target_id)
    ).all()
    tag_reaction_rows = db.execute(
        select(ContentReaction.target_id, func.count(ContentReaction.id))
        .where(
            ContentReaction.target_type == "post",
            ContentReaction.target_id.in_(tagged_post_ids_query),
            ContentReaction.reaction_type.isnot(None),
        )
        .group_by(ContentReaction.target_id)
    ).all()

    tag_comment_map = {int(post_id): int(count or 0) for post_id, count in tag_comment_rows}
    tag_like_map = {int(post_id): int(count or 0) for post_id, count in tag_like_rows}
    tag_reaction_map = {int(post_id): int(count or 0) for post_id, count in tag_reaction_rows}
    tag_views_map = load_post_views_metrics_map(db, tagged_post_ids)

    view_weight = 1
    comment_weight = 30
    like_weight = 12
    reaction_weight = 10

    tag_heat_map: Dict[int, Dict[str, Any]] = {}
    for row in tag_post_rows:
        tag_id = int(row.id)
        post_id = int(row.post_id)
        comment_count = int(tag_comment_map.get(post_id, 0))
        like_count = int(tag_like_map.get(post_id, 0))
        reaction_count = int(tag_reaction_map.get(post_id, 0))
        view_count = int(tag_views_map.get(post_id, 0))

        interaction_score = (
            comment_count * comment_weight
            + like_count * like_weight
            + reaction_count * reaction_weight
        )
        heat_score = interaction_score + view_count * view_weight

        current = tag_heat_map.get(tag_id)
        if current is None:
            current = {
                "id": tag_id,
                "name": row.name,
                "slug": row.slug,
                "count": 0,
                "heat_score": 0,
                "interaction_score": 0,
                "views_score": 0,
            }
            tag_heat_map[tag_id] = current

        current["count"] = int(current["count"]) + 1
        current["heat_score"] = int(current["heat_score"]) + int(heat_score)
        current["interaction_score"] = int(current["interaction_score"]) + int(interaction_score)
        current["views_score"] = int(current["views_score"]) + int(view_count)

    format_hot_tags = sorted(
        tag_heat_map.values(),
        key=lambda item: (
            int(item.get("heat_score", 0)),
            int(item.get("interaction_score", 0)),
            int(item.get("views_score", 0)),
            int(item.get("count", 0)),
            -int(item.get("id", 0)),
        ),
        reverse=True,
    )[:10]
    return format_tag_topic_count, format_hot_tags


def build_format_category_topic_count(db: Session, *, format_post_ids_query) -> int:
    """统计文章格式涉及的分类主题数。"""
    return int(
        db.execute(
            select(func.count(func.distinct(post_categories.c.category_id))).where(
                post_categories.c.post_id.in_(format_post_ids_query)
            )
        ).scalar_one()
        or 0
    )
