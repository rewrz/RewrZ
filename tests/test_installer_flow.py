import re

from fastapi.testclient import TestClient

from rewrz import main as main_module
from rewrz.core.database import db_manager


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


def test_installer_page_allows_incomplete_env_file(monkeypatch, tmp_path):
    _set_installation_complete(monkeypatch, False)
    env_path = tmp_path / ".env"
    monkeypatch.setenv("REWRZ_ENV_FILE", str(env_path))
    env_path.write_text('SECRET_KEY="temp-only"\n', encoding="utf-8")

    client = TestClient(main_module.app)
    response = client.get("/installer", follow_redirects=False)

    assert response.status_code == 200
    assert "开始安装 RewrZ" in response.text


def test_finalize_rolls_back_new_env_file_when_reload_fails(monkeypatch, tmp_path):
    _set_installation_complete(monkeypatch, False)
    env_path = tmp_path / ".env"
    monkeypatch.setenv("REWRZ_ENV_FILE", str(env_path))
    (tmp_path / "data").mkdir()

    client = TestClient(main_module.app)
    step_response = client.get("/installer/step/6")
    csrf_token = _extract_csrf_token(step_response.text)

    monkeypatch.setattr(db_manager, "initialize", lambda: False)

    response = client.post("/installer/finalize", data={"csrf_token": csrf_token})

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert not env_path.exists()


def test_finalize_restores_previous_incomplete_env_file_after_failure(monkeypatch, tmp_path):
    _set_installation_complete(monkeypatch, False)
    env_path = tmp_path / ".env"
    monkeypatch.setenv("REWRZ_ENV_FILE", str(env_path))
    (tmp_path / "data").mkdir()
    original_env = 'COOKIE_SECURE=true\nSESSION_HTTPS_ONLY=true\n'
    env_path.write_text(original_env, encoding="utf-8")

    client = TestClient(main_module.app)
    step_response = client.get("/installer/step/6")
    csrf_token = _extract_csrf_token(step_response.text)

    monkeypatch.setattr(db_manager, "initialize", lambda: False)

    response = client.post("/installer/finalize", data={"csrf_token": csrf_token})

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert env_path.read_text(encoding="utf-8") == original_env
