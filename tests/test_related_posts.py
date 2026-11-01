"""相关文章推荐去重的回归测试。"""

from datetime import datetime
from uuid import uuid4

from rewrz.core.blog_enhancements import get_related_posts
from rewrz.models import Post, Tag

PUBLISHED_AT = datetime(2026, 1, 1, 8, 0, 0)


def _create_post(db, *, title: str, slug: str, tag_ids: list[int]) -> Post:
    """构造已发布文章，并挂上指定标签。"""
    post = Post(
        title=title,
        slug=slug,
        content_markdown="正文",
        content_html="<p>正文</p>",
        excerpt=title,
        post_type="post",
        status="published",
        visibility="public",
        author_id=1,
        published_at=PUBLISHED_AT,
    )
    post.tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def test_related_posts_deduplicates_multi_tag_hits(test_db):
    """同一篇文章命中多个共同标签时，推荐结果里只能出现一次。"""
    suffix = uuid4().hex[:8]
    tag_a = Tag(name=f"去重标签A-{suffix}", slug=f"dedupe-a-{suffix}")
    tag_b = Tag(name=f"去重标签B-{suffix}", slug=f"dedupe-b-{suffix}")
    db = test_db
    db.add_all([tag_a, tag_b])
    db.commit()

    current = _create_post(
        db,
        title="当前文章",
        slug=f"current-{suffix}",
        tag_ids=[tag_a.id, tag_b.id],
    )
    other = _create_post(
        db,
        title="共同标签文章",
        slug=f"other-{suffix}",
        tag_ids=[tag_a.id, tag_b.id],
    )

    related = get_related_posts(db, current, limit=3)
    related_ids = [post.id for post in related]

    assert other.id in related_ids
    assert related_ids.count(other.id) == 1
    assert len(related_ids) == len(set(related_ids))
