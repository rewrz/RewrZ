"""文章浏览量专用表：批量落库、读取与 settings 迁移测试。"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rewrz.core import post_views
from rewrz.core.database import migrate_post_views_out_of_settings
from rewrz.models import PostViewStat
from rewrz.models.base import Base
from rewrz.models.setting import Setting


@contextmanager
def _open_gate(*args, **kwargs):
    yield True


@pytest.fixture(name="engine")
def engine_fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'post-views.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(name="session_factory")
def session_factory_fixture(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _reset_pending():
    with post_views._LOCK:
        post_views._PENDING.clear()
    yield
    with post_views._LOCK:
        post_views._PENDING.clear()


def _patch_writer(monkeypatch, session_factory):
    monkeypatch.setattr(post_views.db_manager, "get_session", lambda: session_factory())
    monkeypatch.setattr(post_views, "background_write_gate", _open_gate)


def test_flush_writes_accumulated_views_into_dedicated_table(
    engine, session_factory, monkeypatch
):
    _patch_writer(monkeypatch, session_factory)
    post_views.increment_post_views(1, 3)
    post_views.increment_post_views(1, 2)
    post_views.increment_post_views(2, 1)

    assert post_views.flush_post_views() == 2
    assert post_views.get_pending_views(1) == 0

    with session_factory() as session:
        rows = {
            int(row.post_id): int(row.views)
            for row in session.execute(select(PostViewStat)).scalars().all()
        }
        assert rows == {1: 5, 2: 1}
        assert session.execute(select(Setting)).scalars().all() == []

    # 第二次落库继续累加，而不是覆盖
    post_views.increment_post_views(1, 4)
    assert post_views.flush_post_views() == 1
    with session_factory() as session:
        row = session.get(PostViewStat, 1)
        assert row is not None and int(row.views) == 9


def test_flush_rejects_when_write_gate_unavailable(engine, session_factory, monkeypatch):
    _patch_writer(monkeypatch, session_factory)

    @contextmanager
    def _busy_gate(*args, **kwargs):
        yield False

    monkeypatch.setattr(post_views, "background_write_gate", _busy_gate)
    post_views.increment_post_views(7, 2)

    assert post_views.flush_post_views() == 0
    # 增量必须回到内存队列，等下轮重试
    assert post_views.get_pending_views(7) == 2
    with session_factory() as session:
        assert session.execute(select(PostViewStat)).scalars().all() == []


def test_load_sum_and_delete_helpers(engine, session_factory):
    with session_factory() as session:
        session.add_all(
            [
                PostViewStat(post_id=11, views=12),
                PostViewStat(post_id=12, views=8),
            ]
        )
        session.commit()

        assert post_views.load_post_views_map(session, [11, 12, 13]) == {11: 12, 12: 8}
        assert post_views.sum_post_views(session) == 20

        post_views.delete_post_view_stats(session, [11])
        session.commit()
        assert post_views.load_post_views_map(session, [11, 12]) == {12: 8}
        assert post_views.sum_post_views(session) == 8


def test_migrate_settings_views_into_post_view_stats(engine, session_factory):
    with session_factory() as session:
        session.add_all(
            [
                Setting(key="post_views_count_9", value={"value": 42}),
                Setting(key="post_views_count_10", value={"value": 7}),
                Setting(key="post_views_count_invalid", value={"value": 5}),
                Setting(key="site_title", value={"value": "站点"}),
                PostViewStat(post_id=9, views=100),
            ]
        )
        session.commit()

    assert migrate_post_views_out_of_settings(engine) == 2

    with session_factory() as session:
        views = {
            int(row.post_id): int(row.views)
            for row in session.execute(select(PostViewStat)).scalars().all()
        }
        # 已存在的指标行取较大值，避免迁移把新写入的浏览量压回去
        assert views == {9: 100, 10: 7}
        remaining_keys = {
            str(row.key) for row in session.execute(select(Setting)).scalars().all()
        }
        assert remaining_keys == {"site_title"}

    # 幂等：没有旧键时直接返回 0
    assert migrate_post_views_out_of_settings(engine) == 0
