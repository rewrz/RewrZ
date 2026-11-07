"""为公开列表与导航页查询补充索引

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-06

说明：
- 公开列表按 post_type + visibility + status 过滤，并按 published_at 倒序分页；
- 模板导航每请求读取已发布的公开页面，按 post_type + status 过滤并排序；
- 现有库没有上述复合索引，这里只做增量创建，兼容既有数据。
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


INDEX_DEFINITIONS = (
    ("ix_posts_public_listing", ["post_type", "visibility", "status", "published_at"]),
    ("ix_posts_page_nav", ["post_type", "status", "published_at"]),
)


def _existing_index_names(inspector, table_name: str) -> set[str]:
    return {item.get("name") for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = _existing_index_names(inspector, "posts")
    for name, columns in INDEX_DEFINITIONS:
        if name in existing:
            continue
        op.create_index(name, "posts", columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = _existing_index_names(inspector, "posts")
    for name, _columns in INDEX_DEFINITIONS:
        if name not in existing:
            continue
        op.drop_index(name, table_name="posts")
