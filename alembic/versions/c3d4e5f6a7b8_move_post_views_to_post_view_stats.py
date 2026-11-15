"""把浏览量从 settings 迁移到 post_view_stats

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-15

说明：
- 浏览量原先按文章写一行 `settings.post_views_count_<id>`，配置表随文章数膨胀，
  设置读取与全表 LIKE 统计都会被拖慢；
- 新表 `post_view_stats` 一篇一行，写入走批量 upsert，读取按主键直取；
- 迁移取新旧值的较大者，避免覆盖迁移期间新产生的浏览量；
- downgrade 不把数据搬回 settings，避免重新制造膨胀。
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _parse_views(raw_value) -> int:
    """兼容 SQLite 的 JSON 文本与 PostgreSQL 已解析的 dict。"""
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, (int, float)):
        return max(0, int(raw_value))
    payload = raw_value
    if isinstance(raw_value, (str, bytes)):
        try:
            payload = json.loads(raw_value)
        except (TypeError, ValueError):
            return 0
    if isinstance(payload, dict):
        payload = payload.get("value")
    try:
        return max(0, int(payload or 0))
    except (TypeError, ValueError):
        return 0


def upgrade() -> None:
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())

    # update.sh 在应用启动前执行迁移，此时新表还不存在，需要先建
    if "post_view_stats" not in table_names:
        op.create_table(
            "post_view_stats",
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("views", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("post_id"),
        )

    if "settings" not in table_names:
        return

    rows = bind.execute(
        sa.text("SELECT key, value FROM settings WHERE key LIKE 'post_views_count_%'")
    ).fetchall()
    if not rows:
        return

    prefix = "post_views_count_"
    metrics: dict[int, int] = {}
    for key, value in rows:
        key_text = str(key or "")
        if not key_text.startswith(prefix):
            continue
        try:
            post_id = int(key_text[len(prefix) :])
        except (TypeError, ValueError):
            continue
        if post_id <= 0:
            continue
        metrics[post_id] = max(metrics.get(post_id, 0), _parse_views(value))

    if metrics:
        bind.execute(
            sa.text(
                "INSERT INTO post_view_stats (post_id, views, updated_at) "
                "VALUES (:post_id, :views, CURRENT_TIMESTAMP) "
                "ON CONFLICT (post_id) DO UPDATE SET "
                "views = CASE WHEN post_view_stats.views > :views "
                "THEN post_view_stats.views ELSE :views END, "
                "updated_at = CURRENT_TIMESTAMP"
            ),
            [{"post_id": post_id, "views": views} for post_id, views in metrics.items()],
        )

    op.execute("DELETE FROM settings WHERE key LIKE 'post_views_count_%'")


def downgrade() -> None:
    """浏览量属于运行数据，不回写 settings，也不删除新表。"""
    pass
