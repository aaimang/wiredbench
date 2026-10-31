"""Test fixtures. Furnidata here is synthetic: no Habbo data is stored in the repo."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from wiredbench.app import create_app
from wiredbench.config import Settings

PASSWORD = "correct horse battery"
PNG = b"\x89PNG\r\n\x1a\n" + b"fakepng"


def furni(classname: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": abs(hash(classname)) % 100000,
        "classname": classname,
        "revision": 100,
        "name": classname.title(),
        "description": f"About {classname}",
        "offerid": 5,
        "bc": True,
        "xdim": 1,
        "ydim": 1,
        **extra,
    }


def furnidata(*floor: dict[str, Any], wall: tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    return {"roomitemtypes": {"furnitype": list(floor)}, "wallitemtypes": {"furnitype": list(wall)}}


class FakeHabbo:
    """Stands in for Habbo's servers and records what was asked."""

    def __init__(self) -> None:
        self.document: dict[str, Any] | bytes = furnidata(furni("chair"), furni("wf_trg_says_something"))
        self.etag = 'W/"v1"'
        self.requests: list[httpx.Request] = []
        self.status: int | None = None
        self.icons: dict[str, bytes] = {}
        self.fail = False
        self.files: dict[str, bytes] = {}
        self.avatar = PNG
        self.profiles: dict[str, dict[str, str]] = {}
        self.status_headers: dict[str, str] = {}

    def set(self, document: dict[str, Any] | bytes, etag: str) -> None:
        self.document, self.etag = document, etag

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("down")
        name = request.url.path.rsplit("/", 1)[1]
        if request.url.host == "images.habbo.com":
            found = self.icons.get(name) or self.files.get(name)
            return httpx.Response(200, content=found) if found else httpx.Response(404)
        if request.url.path.endswith("/avatarimage"):
            return httpx.Response(200, content=self.avatar)
        if request.url.path.endswith("/api/public/users"):
            profile = self.profiles.get(request.url.params["name"])
            return httpx.Response(200, json=profile) if profile else httpx.Response(404)
        if self.status:
            return httpx.Response(self.status, headers=self.status_headers)
        raw = self.document if isinstance(self.document, bytes) else json.dumps(self.document).encode()
        # Like the real thing: /1 redirects to a URL with a hash in it, and only that URL answers 304.
        if request.url.path.endswith("/1"):
            location = f"https://{request.url.host}/gamedata/furnidata_json/{hashlib.sha256(raw).hexdigest()}"
            return httpx.Response(307, headers={"location": location})
        if request.headers.get("if-none-match") == self.etag:
            return httpx.Response(304, headers={"etag": self.etag})
        return httpx.Response(200, content=raw, headers={"etag": self.etag})


class Api:
    """A logged-in test client that sends the CSRF token by itself."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        res = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
        assert res.status_code == 200, res.text
        self.csrf = res.json()["csrf_token"]

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.client.get(url, **kwargs)

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"X-CSRF-Token": self.csrf, **kwargs.pop("headers", {})}
        return self.client.request(method, url, headers=headers, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._send("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._send("PATCH", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._send("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._send("DELETE", url, **kwargs)

    @property
    def services(self) -> Any:
        return self.client.app.state.services  # type: ignore[attr-defined]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    password_file = tmp_path / "password"
    password_file.write_text(PASSWORD)
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        admin_password_file=password_file,
        public_url="http://testserver",
        sync_cooldown_seconds=0,
        static_dir=tmp_path / "no-frontend",
    )


@pytest.fixture
def habbo() -> FakeHabbo:
    return FakeHabbo()


@pytest.fixture
def client(settings: Settings, habbo: FakeHabbo) -> Iterator[TestClient]:
    app = create_app(settings, transport=httpx.MockTransport(habbo))
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
def api(client: TestClient) -> Api:
    return Api(client)


def apply_update(api: Api, hotel: str = "sandbox") -> int:
    res = api.post("/api/catalog/sync", json={"hotel": hotel})
    assert res.status_code == 200, res.text
    version_id = res.json()["version_id"]
    assert api.post("/api/catalog/apply", json={"version_id": version_id}).status_code == 200
    return version_id
