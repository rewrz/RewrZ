"""为标签补充词条释义字段

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-11-11

说明：
- 标签聚合页需要展示一段类似 Wiki 词条的解释文案；
- 字段与分类 description 对齐，允许为空，历史标签不填即为无释义。
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为标签表增加释义列。"""
    op.add_column(
        "tags",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """移除标签释义列。"""
    op.drop_column("tags", "description")
