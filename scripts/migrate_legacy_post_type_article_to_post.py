"""
一次性修复历史 posts.post_type='article' 数据。

用途：
- 移除运行时兼容逻辑后，为仍持有旧数据的环境提供显式修复入口
- 仅做数据收敛，不在应用启动阶段自动执行
"""
from __future__ import annotations

from sqlalchemy import text

from rewrz.core.database import db_manager


def main() -> int:
    db = db_manager.get_session()
    if db is None:
        print("数据库会话创建失败")
        return 1

    try:
        result = db.execute(
            text(
                """
                UPDATE posts
                SET post_type = 'post'
                WHERE post_type = 'article'
                """
            )
        )
        updated_count = int(result.rowcount or 0)
        db.commit()
        print(f"历史 post_type 修复完成，共更新 {updated_count} 条记录。")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"历史 post_type 修复失败：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
