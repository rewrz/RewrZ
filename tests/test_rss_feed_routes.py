"""RSS 订阅路径别名回归测试。

阅读器默认探测的是裸 `/feed`、`/rss`，路由必须与 `.xml` 版本等价，
否则会在探测阶段直接拿到 404。
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core.database import Base, get_db


@pytest.fixture
def rss_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    engine = create_engine(
        f"sqlite:///{tmp_path / f'rss-{uuid4().hex}.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(main_module.app)
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
        engine.dispose()


@pytest.mark.parametrize("path", ["/feed", "/feed.xml", "/rss", "/rss.xml"])
def test_rss_alias_routes_serve_same_feed(rss_client, path):
    response = rss_client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    assert "<rss version=\"2.0\"" in response.text


def test_feed_trailing_slash_redirects_to_bare_path(rss_client):
    response = rss_client.get("/feed/")

    assert response.status_code == 200
    assert "<rss version=\"2.0\"" in response.text
