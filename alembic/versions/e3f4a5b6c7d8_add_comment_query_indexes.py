"""为评论区高频查询补充索引

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-03

说明：
- comments 表在详情页按 post_id + status 过滤并按 created_at 排序；
- 回复树通过 parent_id 查找子级；
- 现有 SQLite 库没有上述索引，这里只做增量创建，兼容既有数据。
"""
from alembic import op
import sqlalchemy as sa

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


INDEX_DEFINITIONS = (
    ("ix_comments_post_status_created", ["post_id", "status", "created_at"]),
    ("ix_comments_parent_id", ["parent_id"]),
)


def _existing_index_names(inspector, table_name: str) -> set[str]:
    return {item.get("name") for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = _existing_index_names(inspector, "comments")
    for name, columns in INDEX_DEFINITIONS:
        if name in existing:
            continue
        op.create_index(name, "comments", columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = _existing_index_names(inspector, "comments")
    for name, _columns in INDEX_DEFINITIONS:
        if name not in existing:
            continue
        op.drop_index(name, table_name="comments")
