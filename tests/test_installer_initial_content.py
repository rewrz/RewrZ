"""安装向导初始内容创建与数据库迁移标记的回归测试。"""

import re

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.models import Category, Format, Post, Tag


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _prepare_installer(monkeypatch, tmp_path) -> TestClient:
    """初始化测试用的安装向导会话与数据库。"""
    _set_installation_complete(monkeypatch, False)
    monkeypatch.setenv("REWRZ_ENV_FILE", str(tmp_path / ".env"))

    client = TestClient(main_module.app)
    database_path = (tmp_path / "data" / "rewrz.db").as_posix()

    step_response = client.get("/installer/step/5")
    assert step_response.status_code == 200
    csrf_token = _extract_csrf_token(step_response.text)

    response = client.post(
        "/installer/initialize-database",
        data={"database_path": database_path, "csrf_token": csrf_token},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    return client


def _connect(tmp_path):
    database_path = (tmp_path / "data" / "rewrz.db").as_posix()
    engine = create_engine(f"sqlite:///{database_path}")
    return sessionmaker(bind=engine)()


def test_step5_preview_matches_backend_definition(monkeypatch, tmp_path):
    """步骤页预览数据必须与后端默认内容定义同源。"""
    client = _prepare_installer(monkeypatch, tmp_path)

    response = client.get("/installer/step/5")
    assert response.status_code == 200
    html = response.text
    assert "技术" in html
    assert "诗词歌赋" in html
    assert "创建 3 个分类" in html


def test_create_default_content_and_idempotent_counts(monkeypatch, tmp_path):
    """勾选默认内容后应创建 3 分类/4 标签/3 内容类型，重复提交计数归零。"""
    client = _prepare_installer(monkeypatch, tmp_path)
    csrf_token = _extract_csrf_token(client.get("/installer/step/5").text)

    form = {
        "csrf_token": csrf_token,
        "create_default_content": "true",
        "create_sample_content": "false",
    }
    response = client.post("/installer/create-initial-content", data=form)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["created"] == {
        "categories": 3,
        "tags": 4,
        "formats": 3,
        "sample_post": False,
    }

    db = _connect(tmp_path)
    try:
        assert len(db.execute(select(Category)).scalars().all()) == 3
        assert len(db.execute(select(Tag)).scalars().all()) == 4
        formats = db.execute(select(Format)).scalars().all()
        assert {fmt.slug for fmt in formats} == {"article", "micro", "poem"}
        assert db.execute(select(Post)).scalars().first() is None
    finally:
        db.close()

    repeat = client.post("/installer/create-initial-content", data=form)
    assert repeat.status_code == 200
    assert repeat.json()["created"] == {
        "categories": 0,
        "tags": 0,
        "formats": 0,
        "sample_post": False,
    }


def test_create_sample_post_with_dependencies(monkeypatch, tmp_path):
    """仅勾选示例文章时，应补齐归属所需的分类、标签与内容类型。"""
    client = _prepare_installer(monkeypatch, tmp_path)

    # 先创建管理员，为示例文章提供作者
    admin_csrf = _extract_csrf_token(client.get("/installer/step/3").text)
    admin_response = client.post(
        "/installer/create-admin",
        data={
            "csrf_token": admin_csrf,
            "username": "admin",
            "email": "admin@example.com",
            "password": "password123",
        },
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["success"] is True

    csrf_token = _extract_csrf_token(client.get("/installer/step/5").text)
    response = client.post(
        "/installer/create-initial-content",
        data={
            "csrf_token": csrf_token,
            "create_default_content": "false",
            "create_sample_content": "true",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["created"]["sample_post"] is True
    assert payload["created"]["categories"] == 1
    assert payload["created"]["tags"] == 1
    assert payload["created"]["formats"] == 3

    db = _connect(tmp_path)
    try:
        post = db.execute(select(Post)).scalars().one()
        assert post.title == "欢迎使用 RewrZ"
        assert post.post_type == "post"
        assert post.author_id == 1
        assert [category.slug for category in post.categories] == ["tech"]
        assert [tag.slug for tag in post.tags] == ["python"]
    finally:
        db.close()


def test_create_sample_post_is_idempotent(monkeypatch, tmp_path):
    """重复提交示例文章不应产生重复内容。"""
    client = _prepare_installer(monkeypatch, tmp_path)
    admin_csrf = _extract_csrf_token(client.get("/installer/step/3").text)
    admin_response = client.post(
        "/installer/create-admin",
        data={
            "csrf_token": admin_csrf,
            "username": "admin",
            "email": "admin@example.com",
            "password": "password123",
        },
    )
    assert admin_response.status_code == 200

    csrf_token = _extract_csrf_token(client.get("/installer/step/5").text)
    form = {
        "csrf_token": csrf_token,
        "create_default_content": "true",
        "create_sample_content": "true",
    }
    assert client.post("/installer/create-initial-content", data=form).status_code == 200
    repeat = client.post("/installer/create-initial-content", data=form)

    assert repeat.status_code == 200
    assert repeat.json()["created"] == {
        "categories": 0,
        "tags": 0,
        "formats": 0,
        "sample_post": False,
    }

    db = _connect(tmp_path)
    try:
        posts = db.execute(select(Post)).scalars().all()
        assert len(posts) == 1
        assert posts[0].slug == "welcome-to-rewrz"
    finally:
        db.close()


def test_initialize_database_stamps_alembic_head(monkeypatch, tmp_path):
    """安装建库后应把新库标记为 Alembic head。"""
    _prepare_installer(monkeypatch, tmp_path)

    db = _connect(tmp_path)
    try:
        stamped = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        db.close()

    config = AlembicConfig("alembic.ini")
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    assert stamped == head_revision
