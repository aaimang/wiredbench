from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient

from wiredbench.app import create_app
from wiredbench.config import Settings
from wiredbench.db import make_engine, migrate
from wiredbench.models import Base


def test_migrations_match_the_models(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "x.db")
    migrate(engine)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []


def test_database_uses_wal_and_foreign_keys(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "x.db")
    migrate(engine)
    with engine.connect() as connection:
        raw = connection.connection
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert sqlite3.sqlite_version_info >= (3, 8)


def built_app(tmp_path: Path, settings: Settings) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Wiredbench</title>")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "assets" / "app-abc.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    settings.static_dir = dist
    return TestClient(create_app(settings), base_url="http://testserver")


def test_frontend_is_served_with_fallback(tmp_path: Path, settings: Settings) -> None:
    client = built_app(tmp_path, settings)
    for path in ("/", "/catalogue", "/workspace/12"):
        res = client.get(path)
        assert res.status_code == 200
        assert "Wiredbench" in res.text
        assert res.headers["cache-control"] == "no-cache"
    assert client.get("/favicon.svg").text == "<svg/>"
    asset = client.get("/assets/app-abc.js")
    assert "immutable" in asset.headers["cache-control"]


def test_unknown_api_paths_are_json_404(tmp_path: Path, settings: Settings) -> None:
    client = built_app(tmp_path, settings)
    for path in ("/api", "/api/nope"):
        res = client.get(path)
        assert res.status_code == 404
        assert res.json()["error"] == "not_found"


def test_path_traversal_cannot_read_files(tmp_path: Path, settings: Settings) -> None:
    client = built_app(tmp_path, settings)
    for path in (
        "/../secret.txt",
        "/assets/../../secret.txt",
        "/assets/%2e%2e/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
    ):
        assert "secret" not in client.get(path).text.replace("secret.txt", ""), path


def test_missing_frontend_gives_clear_message(settings: Settings) -> None:
    client = TestClient(create_app(settings), base_url="http://testserver")
    res = client.get("/")
    assert res.status_code == 503
    assert res.json()["error"] == "frontend_not_built"
