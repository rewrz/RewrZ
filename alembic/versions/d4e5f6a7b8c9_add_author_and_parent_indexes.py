"""补充作者维度与分类树查询索引

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-19

说明：
- 后台与作者归档按 posts.author_id 过滤，SQLite 不会自动为外键建索引；
- 分类树查询按 categories.parent_id 过滤，同样缺少索引；
- 只做增量创建，已存在同名索引时跳过。
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


INDEX_DEFINITIONS = (
    ("ix_posts_author_id", "posts", ["author_id"]),
    ("ix_categories_parent_id", "categories", ["parent_id"]),
)


def _existing_index_names(inspector, table_name: str) -> set[str]:
    return {item.get("name") for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {}
    for _name, table_name, _columns in INDEX_DEFINITIONS:
        if table_name not in existing_indexes:
            existing_indexes[table_name] = _existing_index_names(inspector, table_name)
    for name, table_name, columns in INDEX_DEFINITIONS:
        if name in existing_indexes[table_name]:
            continue
        op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {}
    for _name, table_name, _columns in INDEX_DEFINITIONS:
        if table_name not in existing_indexes:
            existing_indexes[table_name] = _existing_index_names(inspector, table_name)
    for name, table_name, _columns in INDEX_DEFINITIONS:
        if name not in existing_indexes[table_name]:
            continue
        op.drop_index(name, table_name=table_name)
