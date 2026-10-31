"""clear categories for micro and poem posts

Revision ID: c1d2e3f4a5b6
Revises:
Create Date: 2026-10-31 12:00:00.000000

说明：项目自本迁移起重新跟踪 Alembic，历史迁移已全部废弃并删除。
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """微博/诗词不再支持分类，清理已有的分类关联。"""
    op.execute(
        """
        DELETE FROM post_categories
        WHERE post_id IN (
            SELECT pf.post_id
            FROM post_formats AS pf
            JOIN formats AS f ON f.id = pf.format_id
            WHERE LOWER(f.slug) IN ('micro', 'poem')
        )
        """
    )


def downgrade() -> None:
    """分类关联属于用户数据，不做自动恢复。"""
    pass
