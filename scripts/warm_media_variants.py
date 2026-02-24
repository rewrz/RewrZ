"""
媒体变体预热脚本

用途：
1. 为历史图片批量生成媒体库预览变体，减少首次打开媒体库卡顿。
2. 可选预热其它预设。

默认行为：
- 仅预热 `media_lib_card`
- dpr=1
- fmt=jpg
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rewrz.core.database import get_db  # noqa: E402
from rewrz.core.thumbnail_service import generate_media_variant  # noqa: E402
from rewrz.models.media import Media  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预热媒体缩略图变体缓存")
    parser.add_argument("--preset", default="media_lib_card", help="预设名称，默认 media_lib_card")
    parser.add_argument("--dpr", type=int, default=1, help="设备像素比，默认 1")
    parser.add_argument("--fmt", default="jpg", help="输出格式，默认 jpg")
    parser.add_argument("--limit", type=int, default=0, help="最多处理数量，0 表示不限制")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db = next(get_db())
    try:
        stmt = select(Media).where(Media.file_type == "image").order_by(Media.id.asc())
        if args.limit and args.limit > 0:
            stmt = stmt.limit(args.limit)
        rows = db.execute(stmt).scalars().all()

        total = len(rows)
        success = 0
        failed = 0
        print(f"准备预热 {total} 张图片：preset={args.preset}, dpr={args.dpr}, fmt={args.fmt}")
        for idx, media in enumerate(rows, start=1):
            try:
                generate_media_variant(
                    db=db,
                    media_obj=media,
                    preset_name=args.preset,
                    dpr=args.dpr,
                    fmt=args.fmt,
                    accept_header="image/jpeg,image/*,*/*",
                )
                success += 1
            except Exception as exc:
                failed += 1
                print(f"[{idx}/{total}] 失败 media_id={media.id}: {exc}")
                continue
            if idx % 50 == 0 or idx == total:
                print(f"[{idx}/{total}] 已完成，成功={success}，失败={failed}")

        print(f"预热结束：总数={total}，成功={success}，失败={failed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
