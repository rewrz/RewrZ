"""公开页缓存命中与未命中的本地容量基准。

用法（仓库根目录）：
    .\\.venv\\Scripts\\python.exe scripts/benchmark_capacity.py

使用临时 SQLite 库与 FastAPI TestClient，不访问真实站点数据、不发网络请求。
TestClient 是单线程同步客户端，结果用于比较「命中 / 未命中」的相对成本，
不能直接当作生产并发吞吐；上线前按 DEPLOYMENT.md 7.10 用真实压测复核。
"""
from __future__ import annotations

import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from rewrz import main as main_module  # noqa: E402
from rewrz.core import public_detail_cache, public_list_cache  # noqa: E402
from rewrz.core.database import Base, get_db  # noqa: E402
from rewrz.models import Post, User as DbUser  # noqa: E402


def _prepare_database(engine):
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_local() as db:
        db.add(
            DbUser(
                id=1,
                username="bench-admin",
                hashed_password="hashed",
                email="bench@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
            )
        )
        db.add(
            Post(
                title="容量基准文章",
                slug="bench-article",
                content_markdown="基准正文" * 20,
                content_html="<p>" + "基准正文" * 20 + "</p>",
                excerpt="基准正文",
                post_type="post",
                status="published",
                visibility="public",
                published_at=datetime(2026, 1, 1, 8, 0, 0),
                author_id=1,
            )
        )
        db.commit()
    return session_local


def _timed_requests(client, urls, label):
    samples = []
    for url in urls:
        started = time.perf_counter()
        response = client.get(url)
        samples.append((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            raise RuntimeError(f"{label} 请求 {url} 返回 {response.status_code}")
    return statistics.mean(samples), statistics.median(samples)


def main() -> int:
    # 只影响本进程：让公开路由走完整流程，不依赖真实 .env 的安装状态
    type(main_module.settings).installation_complete = property(lambda self: True)

    with tempfile.TemporaryDirectory(prefix="rewrz-bench-") as tmp_dir:
        engine = create_engine(
            f"sqlite:///{Path(tmp_dir) / 'bench.db'}",
            connect_args={"check_same_thread": False},
        )
        session_local = _prepare_database(engine)

        sql_count = [0]

        @event.listens_for(engine, "before_cursor_execute")
        def _count_sql(conn, cursor, statement, parameters, context, executemany):
            sql_count[0] += 1

        def override_get_db():
            db = session_local()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[get_db] = override_get_db
        public_list_cache.clear_public_list_cache()
        public_detail_cache.clear_public_detail_cache()

        prepare_calls = [0]
        original_prepare = main_module._prepare_request_state

        def counting_prepare(request):
            prepare_calls[0] += 1
            return original_prepare(request)

        main_module._prepare_request_state = counting_prepare

        try:
            client = TestClient(main_module.app)
            assert client.get("/").status_code == 200
            assert client.get("/article/bench-article").status_code == 200

            prepare_calls[0] = 0
            sql_count[0] = 0
            list_hit_mean, list_hit_median = _timed_requests(
                client, ["/"] * 200, "列表缓存命中"
            )
            list_sql = sql_count[0]
            sql_count[0] = 0
            detail_hit_mean, detail_hit_median = _timed_requests(
                client, ["/article/bench-article"] * 200, "详情缓存命中"
            )
            detail_sql = sql_count[0]
            hit_prepare_calls = prepare_calls[0]
            sql_count[0] = 0
            miss_mean, miss_median = _timed_requests(
                client,
                [f"/article/bench-article?bench={index}" for index in range(20)],
                "缓存未命中",
            )
            miss_sql = sql_count[0]

            print("=== 公开页缓存容量基准（单线程 TestClient，仅比较相对成本）===")
            print(f"列表缓存命中 200 次：平均 {list_hit_mean:.2f} ms / 中位 {list_hit_median:.2f} ms / SQL {list_sql} 条")
            print(f"详情缓存命中 200 次：平均 {detail_hit_mean:.2f} ms / 中位 {detail_hit_median:.2f} ms / SQL {detail_sql} 条")
            print(f"缓存未命中 20 次：平均 {miss_mean:.2f} ms / 中位 {miss_median:.2f} ms / SQL {miss_sql} 条")
            print(f"命中阶段建请求级会话次数：{hit_prepare_calls}（应为 0）")
            if list_hit_mean > 0 and miss_mean > 0:
                print(f"未命中 / 列表命中 成本比：{miss_mean / list_hit_mean:.1f} 倍")
            print()
            print("容量口径：100 万 PV/日 ≈ 平均 11.6 req/s，10 倍峰值约 116 req/s。")
            print("按 CDN 命中 90% + 应用内缓存命中 90% 估算，回源渲染约 1.2 req/s（峰值）。")
            print("若未命中渲染耗时 T 秒，单 worker 渲染上限约 1/T req/s；请以真实压测复核。")
            return 0
        finally:
            main_module._prepare_request_state = original_prepare
            main_module.app.dependency_overrides.pop(get_db, None)
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
