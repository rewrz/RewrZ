from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Any

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rewrz.core.database import db_manager
from rewrz.core.data_manager import WordPressImporter
from rewrz.crud import setting as crud_setting
from rewrz.models import Post, User


def _load_wp_import_options(db) -> Dict[str, Any]:
    setting = crud_setting.get_setting(db, "wordpress_import_options")
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    options = dict(value)
    options["download_remote_media"] = True
    options["media_download_timeout_seconds"] = 8
    return options


def main() -> int:
    db_manager.reload_if_needed()
    db = db_manager.get_session()
    if db is None:
        print("数据库未初始化，无法执行封面图本地化修复。")
        return 1

    try:
        importer = WordPressImporter(db, options=_load_wp_import_options(db))
        default_uploader_id = db.execute(select(User.id).order_by(User.id.asc())).scalars().first()
        posts = db.execute(
            select(Post).where(Post.featured_image_url.is_not(None))
        ).scalars().all()

        scanned = 0
        localized = 0
        skipped = 0
        failed = 0

        for post in posts:
            featured_image_url = str(post.featured_image_url or "").strip()
            if not featured_image_url:
                skipped += 1
                continue
            if not importer._is_remote_http_url(featured_image_url):
                skipped += 1
                continue

            scanned += 1
            try:
                local_url = importer._download_media_and_get_local_url(
                    featured_image_url,
                    source_link="",
                    uploaded_by_id=post.author_id or default_uploader_id,
                    reference_datetime=post.published_at or post.created_at,
                )
                if local_url and local_url.startswith("/media/") and local_url != featured_image_url:
                    post.featured_image_url = local_url
                    db.commit()
                    localized += 1
                else:
                    failed += 1
            except Exception as exc:
                db.rollback()
                failed += 1
                importer._record_media_download_failure(featured_image_url, str(exc))

            if scanned % 20 == 0:
                print(f"已扫描 {scanned} 条，已成功本地化 {localized} 条。")

        print(f"扫描外链封面图：{scanned}")
        print(f"成功本地化：{localized}")
        print(f"跳过无需处理：{skipped}")
        print(f"处理失败：{failed}")
        if importer._media_download_failures:
            print("失败明细：")
            for item in importer._media_download_failures:
                print(f"- {item['url']} -> {item['reason']}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"封面图本地化修复失败：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
