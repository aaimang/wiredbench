from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from conftest import PASSWORD, Api
from wiredbench.app import create_app
from wiredbench.config import Settings
from wiredbench.models import AuthSession, utcnow

NEW_PASSWORD = "a different long password"


def test_login_me_logout(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    api = Api(client)
    me = api.get("/api/auth/me").json()
    assert me["username"] == "admin"
    assert me["csrf_token"] == api.csrf
    assert api.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_bad_login_messages_are_identical(client: TestClient) -> None:
    wrong_password = client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    wrong_user = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert wrong_password.status_code == wrong_user.status_code == 401
    assert wrong_password.json() == wrong_user.json()


def test_expired_session_is_refused(api: Api) -> None:
    with api.services.sessions.begin() as db:
        db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
    assert api.get("/api/auth/me").status_code == 401


def test_change_password(api: Api, client: TestClient, settings: Settings) -> None:
    other = TestClient(client.app, base_url="http://testserver")
    Api(other)
    res = api.post(
        "/api/auth/password", json={"current_password": "nope nope nope", "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 403
    assert (
        api.post(
            "/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
        ).status_code
        == 422
    )
    res = api.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert res.status_code == 204
    assert api.get("/api/auth/me").status_code == 200, "this session stays signed in"
    assert other.get("/api/auth/me").status_code == 401, "other sessions are signed out"
    login = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert login.status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": NEW_PASSWORD}).status_code
        == 200
    )


def test_generated_password_is_saved_and_removed_after_change(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", public_url="http://testserver")
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        password = settings.initial_password_path.read_text().strip()
        assert len(password) >= 20
        res = client.post("/api/auth/login", json={"username": "admin", "password": password})
        csrf = res.json()["csrf_token"]
        res = client.post(
            "/api/auth/password",
            json={"current_password": password, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 204
        assert not settings.initial_password_path.exists()


def test_generated_password_never_reaches_the_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", public_url="http://testserver")
    create_app(settings)
    assert settings.initial_password_path.read_text().strip() not in caplog.text


def test_short_password_file_is_refused(tmp_path: Path) -> None:
    file = tmp_path / "p"
    file.write_text("short")
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", admin_password_file=file)
    with pytest.raises(SystemExit):
        create_app(settings)


def test_restart_keeps_the_admin(tmp_path: Path, settings: Settings) -> None:
    create_app(settings)
    settings.admin_password_file = None
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        assert (
            client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}).status_code
            == 200
        )
    assert not settings.initial_password_path.exists()
