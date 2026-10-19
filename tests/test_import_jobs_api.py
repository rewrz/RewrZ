"""
异步导入任务测试模块

覆盖多 worker 部署下的核心回归场景：
1. 任务状态跨"进程"（独立引擎/会话）可见——修复进程内内存字典导致轮询 404 的问题
2. 任务查询端点的 200/403/404 契约与 user_id 不泄漏
3. 僵死任务（心跳超时）自动收敛为 interrupted
4. 终态任务过期清理
5. 进度落库节流策略
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.api import data_import_export
from rewrz.core.database import db_manager
from rewrz.models import Base, ImportJob


@pytest.fixture(name="shared_db_path")
def shared_db_path_fixture(tmp_path):
    """两个独立引擎共享的 SQLite 文件，用于模拟多 worker 部署。"""
    return tmp_path / "import_jobs_shared.db"


def _make_session(db_path):
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_job_status_visible_across_independent_engines(shared_db_path):
    """核心回归：一个"进程"创建的任务，另一个"进程"必须能查询到。"""
    worker_a_db = _make_session(shared_db_path)
    worker_b_db = _make_session(shared_db_path)
    try:
        job_id = data_import_export._create_import_job(
            worker_a_db, user_id=7, job_type="wordpress_import", filename="demo.xml"
        )
        worker_a_db.close()

        # worker B 使用完全独立的引擎与会话（等价于另一个 uvicorn worker 进程）
        job = data_import_export._get_import_job(worker_b_db, job_id)

        assert job is not None
        assert job["id"] == job_id
        assert job["status"] == "queued"
        assert job["type"] == "wordpress_import"
        assert job["progress"]["stage"] == "queued"
        # user_id 仅用于权限校验，转换函数必须保留该字段
        assert job["user_id"] == 7
    finally:
        worker_b_db.close()


def test_import_job_to_dict_keeps_user_id_for_authorization():
    """转换字典必须保留 user_id 供端点做权限校验（响应前由端点剥离）。"""
    job = ImportJob(
        id="abc123",
        user_id=42,
        job_type="wordpress_import",
        filename="demo.xml",
        status="running",
        progress_stage="posts",
        progress_message="正在导入文章 (1/2)",
        progress_current=1,
        progress_total=2,
        progress_percent=50,
    )
    view = data_import_export._import_job_to_dict(job)
    assert view["user_id"] == 42
    assert view["progress"] == {
        "stage": "posts",
        "message": "正在导入文章 (1/2)",
        "current": 1,
        "total": 2,
        "percent": 50,
    }


def test_import_job_to_dict_merges_progress_extra():
    job = ImportJob(
        id="abc123",
        user_id=1,
        job_type="wordpress_import",
        status="running",
        progress_stage="posts",
        progress_message="导入中",
        progress_extra={"stats": {"posts_imported": 3}},
    )
    view = data_import_export._import_job_to_dict(job)
    assert view["progress"]["stats"] == {"posts_imported": 3}


def test_stale_running_job_marked_interrupted(test_db):
    """心跳超时的 running 任务应被收敛为 interrupted，避免前端无限轮询。"""
    job = ImportJob(
        id="stale01",
        user_id=1,
        job_type="wordpress_import",
        status="running",
        worker_pid=999999,
        heartbeat_at=datetime.utcnow() - timedelta(seconds=data_import_export._IMPORT_JOB_STALE_SECONDS + 30),
    )
    test_db.add(job)
    test_db.commit()

    result = data_import_export._get_import_job(test_db, "stale01")

    assert result["status"] == "interrupted"
    assert "中断" in result["error"]


def test_fresh_heartbeat_job_stays_running(test_db):
    """心跳新鲜的 running 任务不得被误判为中断。"""
    job = ImportJob(
        id="fresh01",
        user_id=1,
        job_type="wordpress_import",
        status="running",
        worker_pid=1,
        heartbeat_at=datetime.utcnow() - timedelta(seconds=10),
    )
    test_db.add(job)
    test_db.commit()

    result = data_import_export._get_import_job(test_db, "fresh01")

    assert result["status"] == "running"


def test_running_job_without_heartbeat_not_interrupted(test_db):
    """刚进入 running 尚未写首次心跳的任务不判定僵死，交给下一次轮询。"""
    job = ImportJob(
        id="nohb001",
        user_id=1,
        job_type="wordpress_import",
        status="running",
        heartbeat_at=None,
    )
    test_db.add(job)
    test_db.commit()

    result = data_import_export._get_import_job(test_db, "nohb001")
    assert result["status"] == "running"


def test_cleanup_expired_import_jobs(test_db):
    """超过保留时长的终态任务被清理，未终态任务保留。"""
    now = datetime.utcnow()
    old = now - timedelta(seconds=data_import_export._IMPORT_JOB_RETENTION_SECONDS + 60)
    recent = now - timedelta(seconds=3600)
    test_db.add_all([
        ImportJob(id="olddone", user_id=1, job_type="wordpress_import", status="completed", created_at=old),
        ImportJob(id="oldfail", user_id=1, job_type="wordpress_import", status="failed", created_at=old),
        ImportJob(id="oldrun", user_id=1, job_type="wordpress_import", status="running", created_at=old),
        ImportJob(id="newdone", user_id=1, job_type="wordpress_import", status="completed", created_at=recent),
    ])
    test_db.commit()

    data_import_export._cleanup_expired_import_jobs(test_db)

    remaining = {row[0] for row in test_db.query(ImportJob.id).all()}
    assert "olddone" not in remaining
    assert "oldfail" not in remaining
    assert "oldrun" in remaining
    assert "newdone" in remaining


def test_should_write_progress_throttle_and_force():
    """同阶段连续更新按节流合并；阶段切换与终态立即落库。"""
    job_id = "throttle1"
    data_import_export._PROGRESS_THROTTLE_STATE.pop(job_id, None)
    try:
        assert data_import_export._should_write_progress(job_id, "posts") is True
        # 同阶段、间隔内的连续更新被合并
        assert data_import_export._should_write_progress(job_id, "posts") is False
        # 阶段切换立即写入
        assert data_import_export._should_write_progress(job_id, "tags") is True
        # 终态强制写入
        assert data_import_export._should_write_progress(job_id, "tags") is False
        assert data_import_export._should_write_progress(job_id, "completed") is True
        assert data_import_export._should_write_progress(job_id, "failed") is True
    finally:
        data_import_export._PROGRESS_THROTTLE_STATE.pop(job_id, None)


@pytest.fixture(name="api_client")
def api_client_fixture(test_db, monkeypatch):
    """挂载依赖覆写的 TestClient，使用测试数据库与固定用户。"""
    admin_path = main_module.settings.ADMIN_PATH.rstrip("/")
    fake_user = SimpleNamespace(id=1)

    monkeypatch.setattr(db_manager, "reload_if_needed", lambda: True)
    monkeypatch.setattr(db_manager, "get_session", lambda: test_db)
    monkeypatch.setattr(data_import_export, "verify_csrf_token", lambda *args, **kwargs: None)

    from rewrz.main import app

    app.dependency_overrides[data_import_export.get_db] = lambda: test_db
    app.dependency_overrides[data_import_export.get_current_user] = lambda: fake_user
    client = TestClient(app)
    try:
        yield client, admin_path
    finally:
        app.dependency_overrides.pop(data_import_export.get_db, None)
        app.dependency_overrides.pop(data_import_export.get_current_user, None)


def test_get_job_status_endpoint_returns_job(api_client, test_db):
    client, admin_path = api_client
    job = ImportJob(
        id="api0001",
        user_id=1,
        job_type="wordpress_import",
        filename="demo.xml",
        status="running",
        progress_stage="posts",
        progress_message="正在导入文章 (2/5)",
        progress_current=2,
        progress_total=5,
        progress_percent=40,
    )
    test_db.add(job)
    test_db.commit()

    response = client.get(f"{admin_path}/api/v1/import/jobs/api0001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["job"]["id"] == "api0001"
    assert payload["job"]["status"] == "running"
    assert payload["job"]["progress"]["percent"] == 40
    assert "user_id" not in payload["job"]


def test_get_job_status_endpoint_404_for_missing_job(api_client):
    client, admin_path = api_client
    response = client.get(f"{admin_path}/api/v1/import/jobs/notexist")

    assert response.status_code == 404
    # 错误体为嵌套结构，message 可读
    assert response.json()["error"]["message"] == "任务不存在或已过期"


def test_get_job_status_endpoint_403_for_other_user(api_client, test_db):
    client, admin_path = api_client
    test_db.add(ImportJob(id="api0002", user_id=999, job_type="wordpress_import", status="completed"))
    test_db.commit()

    response = client.get(f"{admin_path}/api/v1/import/jobs/api0002")

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "无权访问该任务"


def test_create_wordpress_import_task_endpoint(api_client, test_db, monkeypatch, tmp_path):
    client, admin_path = api_client
    submitted = {}

    class _ExecutorStub:
        def submit(self, fn, *args, **kwargs):
            submitted["fn"] = fn
            submitted["args"] = args

    monkeypatch.setattr(data_import_export, "_IMPORT_EXECUTOR", _ExecutorStub())

    response = client.post(
        f"{admin_path}/api/v1/import/wordpress/tasks",
        files={"wxr_file": ("wordpress.xml", b"<rss version=\"2.0\"></rss>", "application/xml")},
        headers={"X-CSRF-Token": "test-csrf-token"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is True
    job_id = payload["job_id"]

    # 任务记录在任何"进程"均可读到的数据库中
    job = test_db.get(ImportJob, job_id)
    assert job is not None
    assert job.status == "queued"
    assert job.user_id == 1
    assert submitted["args"][0] == job_id
