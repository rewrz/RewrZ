"""add content_rating to posts

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-01 00:00:00.000000

说明：内容分级只作用于发布单元（文章/页面），取值 general / sensitive / nsfw。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为文章与页面补充内容分级字段，历史数据默认为通用内容。"""
    op.add_column(
        "posts",
        sa.Column(
            "content_rating",
            sa.String(),
            nullable=False,
            server_default="general",
        ),
    )


def downgrade() -> None:
    """回滚时移除内容分级字段。"""
    op.drop_column("posts", "content_rating")
