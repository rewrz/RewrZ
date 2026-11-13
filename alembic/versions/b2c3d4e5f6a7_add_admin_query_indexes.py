"""为后台列表与统计查询补充索引

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-13

说明：
- 后台文章/页面列表按 created_at 倒序分页，状态筛选单独按 status 过滤；
- 后台评论审核按 status 过滤并按 created_at 倒序，仪表盘按状态统计评论；
- 后台分类/标签/格式筛选走关联表的反向列，联合主键最左列是 post_id；
- create_all 只会建缺失的表，不会给既有表补索引，这里只做增量创建。
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


INDEX_DEFINITIONS = (
    ("posts", "ix_posts_status", ["status"]),
    ("posts", "ix_posts_created_at", ["created_at"]),
    ("comments", "ix_comments_status_created", ["status", "created_at"]),
    ("post_categories", "ix_post_categories_category_id", ["category_id"]),
    ("post_tags", "ix_post_tags_tag_id", ["tag_id"]),
    ("post_formats", "ix_post_formats_format_id", ["format_id"]),
)


def _existing_index_names(inspector, table_name: str) -> set[str]:
    return {item.get("name") for item in inspector.get_indexes(table_name)}


def _index_names_by_table(inspector) -> dict[str, set[str]]:
    return {
        table_name: _existing_index_names(inspector, table_name)
        for table_name in {item[0] for item in INDEX_DEFINITIONS}
    }


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = _index_names_by_table(inspector)
    for table_name, name, columns in INDEX_DEFINITIONS:
        if name in existing[table_name]:
            continue
        op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = _index_names_by_table(inspector)
    for table_name, name, _columns in INDEX_DEFINITIONS:
        if name not in existing[table_name]:
            continue
        op.drop_index(name, table_name=table_name)
