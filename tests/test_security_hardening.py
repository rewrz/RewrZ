import io
import zipfile
from types import SimpleNamespace

import anyio
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.api import data_import_export as data_api
from rewrz.api import media as media_api
from rewrz.core.config import settings
from rewrz.core.security import get_current_user


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def _override_login_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, username="tester", email="tester@example.com", role="super_admin")


def test_categories_create_requires_login(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    client = TestClient(main_module.app)
    admin_prefix = settings.ADMIN_PATH.rstrip("/")
    response = client.post(f"{admin_prefix}/api/v1/categories/", data={"name": "分类A"})
    assert response.status_code == 401


def test_categories_create_requires_csrf_header_when_logged_in(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    main_module.app.dependency_overrides[get_current_user] = _override_login_user
    client = TestClient(main_module.app)
    admin_prefix = settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.post(f"{admin_prefix}/api/v1/categories/", data={"name": "分类A"})
        assert response.status_code == 422
    finally:
        main_module.app.dependency_overrides.clear()


def test_tags_create_requires_csrf_header_when_logged_in(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    main_module.app.dependency_overrides[get_current_user] = _override_login_user
    client = TestClient(main_module.app)
    admin_prefix = settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.post(f"{admin_prefix}/api/v1/tags/", data={"name": "标签A"})
        assert response.status_code == 422
    finally:
        main_module.app.dependency_overrides.clear()


def test_anniversary_save_requires_csrf_header_when_logged_in(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    main_module.app.dependency_overrides[get_current_user] = _override_login_user
    client = TestClient(main_module.app)
    try:
        response = client.post("/api/v1/anniversary-mode/save", json={"anniversaries": []})
        assert response.status_code == 422
    finally:
        main_module.app.dependency_overrides.clear()


def test_import_options_requires_csrf_header_when_logged_in(monkeypatch):
    _set_installation_complete(monkeypatch, True)
    main_module.app.dependency_overrides[get_current_user] = _override_login_user
    client = TestClient(main_module.app)
    admin_prefix = settings.ADMIN_PATH.rstrip("/")
    try:
        response = client.post(f"{admin_prefix}/api/v1/import/wordpress/options", json={})
        assert response.status_code == 422
    finally:
        main_module.app.dependency_overrides.clear()


def test_installer_initialize_database_requires_csrf_form_field(monkeypatch):
    _set_installation_complete(monkeypatch, False)
    client = TestClient(main_module.app)
    response = client.post("/installer/initialize-database", data={"database_path": "./data/test.db"})
    assert response.status_code == 422


def test_extract_backup_zip_safely_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "path_traversal.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
        zip_handle.writestr("../evil.txt", "x")

    with pytest.raises(HTTPException) as exc_info:
        data_api._extract_backup_zip_safely(str(zip_path), str(tmp_path / "extract"))

    assert exc_info.value.status_code == 400
    assert "非法路径" in str(exc_info.value.detail) or "越界路径" in str(exc_info.value.detail)


def test_extract_backup_zip_safely_rejects_abnormal_compression_ratio(tmp_path):
    zip_path = tmp_path / "high_ratio.zip"
    large_repeated_content = b"a" * (2 * 1024 * 1024)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
        zip_handle.writestr("data/payload.txt", large_repeated_content)

    with pytest.raises(HTTPException) as exc_info:
        data_api._extract_backup_zip_safely(str(zip_path), str(tmp_path / "extract"))

    assert exc_info.value.status_code == 400
    assert "压缩比异常" in str(exc_info.value.detail)


def test_media_upload_stream_rejects_oversized_file(tmp_path):
    async def _run() -> None:
        target = tmp_path / "oversized.bin"
        upload = UploadFile(filename="oversized.bin", file=io.BytesIO(b"a" * 32))
        with pytest.raises(HTTPException) as exc_info:
            await media_api._write_upload_stream_to_file(upload, target, max_size=16)
        assert exc_info.value.status_code == 400
        assert target.exists() is True
        assert target.stat().st_size == 0

    anyio.run(_run)
