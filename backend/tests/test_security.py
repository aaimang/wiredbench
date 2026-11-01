"""The rules that keep outsiders out. These walk every route, so a new route is covered by default."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import PASSWORD, Api, FakeHabbo
from wiredbench.api import ROUTERS
from wiredbench.app import create_app
from wiredbench.config import Settings
from wiredbench.models import AuthSession
from wiredbench.security import RateLimiter, same_origin

PUBLIC = {("POST", "/api/auth/login"), ("GET", "/healthz"), ("GET", "/{path:path}")}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
MOCK = "/api/public/rooms/"  # These use the mock API's own keys. test_mock_api.py covers them.


def fill(path: str) -> str:
    path = path.replace("{kind}", "folder").replace("{classname}", "chair")
    return re.sub(r"\{[^}]+\}", "1", path)


def api_routes(client: TestClient) -> list[APIRoute]:
    routes = [route for route in client.app.routes if isinstance(route, APIRoute)]  # type: ignore[attr-defined]
    for router in ROUTERS:
        routes += [route for route in router.routes if isinstance(route, APIRoute)]
    return routes


def all_routes(client: TestClient) -> list[tuple[str, str]]:
    return [(method, r.path) for r in api_routes(client) for method in r.methods if method != "HEAD"]


def test_there_are_routes_to_check(client: TestClient) -> None:
    # FastAPI changed how included routers are stored once. If that happens again, the walks below
    # would silently check nothing, so this count must stay honest.
    assert len(all_routes(client)) > 30
    assert ("POST", "/api/catalog/sync") in all_routes(client)
    assert ("DELETE", "/api/trash/{kind}/{item_id}") in all_routes(client)


def test_only_expected_routes_are_public(client: TestClient) -> None:
    found = {
        (method, route.path)
        for route in api_routes(client)
        if getattr(route.endpoint, "__wb_public__", False)
        for method in route.methods
        if method != "HEAD"
    }
    mock_routes = {route for route in found if route[1].startswith(MOCK)}
    assert found - mock_routes == PUBLIC
    assert len(mock_routes) >= 18


def test_outsiders_get_401_on_every_private_route(client: TestClient) -> None:
    for method, path in all_routes(client):
        if (method, path) in PUBLIC or path.startswith(MOCK):
            continue
        res = client.request(method, fill(path), json={})
        assert res.status_code == 401, f"{method} {path} gave {res.status_code}"
        assert res.json()["error"] == "not_logged_in"


def test_writes_without_csrf_get_403_on_every_route(api: Api) -> None:
    for method, path in all_routes(api.client):
        if method not in UNSAFE or (method, path) in PUBLIC or path.startswith(MOCK):
            continue
        res = api.client.request(method, fill(path), json={})
        assert res.status_code == 403, f"{method} {path} gave {res.status_code}"
        assert res.json()["error"] == "bad_csrf"


def test_mock_routes_give_outsiders_nothing(api: Api, client: TestClient) -> None:
    room = api.post("/api/tutorials/time-tracking", json={}).json()["id"]
    api.post(f"/api/sandboxes/{room}/run", json={"seed": 1})
    api.post(f"/api/sandboxes/{room}/api-keys", json={})
    outsider = TestClient(client.app, base_url="http://testserver")
    checked = 0
    for method, path in all_routes(client):
        if path.startswith(MOCK):
            checked += 1
            url = fill(
                path.replace("{scope}", "user").replace("{kind}", "users").replace("{room_id}", str(room))
            )
            res = outsider.request(method, url, json={"value": 1, "requests": [], "variables": {}})
            assert res.status_code in (400, 403, 404), f"{method} {path} gave {res.status_code}"
    assert checked >= 18


def test_wrong_csrf_token_is_refused(api: Api) -> None:
    res = api.client.post("/api/folders", json={"name": "x"}, headers={"X-CSRF-Token": "wrong"})
    assert res.status_code == 403


def test_other_site_origin_is_refused(api: Api) -> None:
    res = api.post("/api/folders", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    assert res.json()["error"] == "bad_origin"
    res = api.client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_wrong_host_is_refused(client: TestClient) -> None:
    # Blocks DNS rebinding, where a hostile domain points at a local install.
    assert client.get("/healthz", headers={"Host": "evil.example"}).status_code == 400


def test_session_cookie_flags(client: TestClient) -> None:
    res = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie  # http://testserver.


def test_https_install_sets_secure_cookie(tmp_path: Path) -> None:
    file = tmp_path / "p"
    file.write_text(PASSWORD)
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "d", admin_password_file=file, public_url="https://wb.example"
    )
    assert settings.secure_cookies


def test_session_tokens_are_stored_hashed(api: Api) -> None:
    token = api.client.cookies["wb_session"]
    with api.services.sessions() as db:
        stored = db.scalars(select(AuthSession.token_hash)).all()
    assert stored
    assert token not in stored


def test_security_headers_on_api_and_errors(client: TestClient) -> None:
    for url in ("/healthz", "/api/settings", "/api/nope"):
        headers = client.get(url).headers
        assert "script-src 'self'" in headers["content-security-policy"]
        assert "unsafe" not in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-robots-tag"] == "noindex"


def test_api_docs_are_not_exposed(client: TestClient) -> None:
    for url in ("/docs", "/redoc", "/openapi.json"):
        res = client.get(url)
        assert b"swagger" not in res.content.lower()
        assert b'"openapi"' not in res.content


def test_body_limit(api: Api) -> None:
    res = api.post("/api/folders", content=b"x" * (3 * 2**20), headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_validation_error_does_not_echo_input(api: Api) -> None:
    res = api.post("/api/folders", json={"name": "<script>alert(1)</script>" * 20})
    assert res.status_code == 422
    assert "<script>" not in res.text


def test_sql_injection_is_treated_as_text(api: Api) -> None:
    attack = "x'; DROP TABLE folder; --"
    assert api.post("/api/folders", json={"name": attack}).status_code == 201
    assert api.get("/api/catalog/items", params={"q": attack}).status_code == 200
    names = [f["name"] for f in api.get("/api/workspace/tree").json()["folders"]]
    assert names == [attack]


def test_search_wildcards_are_literal(api: Api, habbo: FakeHabbo) -> None:
    from conftest import apply_update

    apply_update(api)
    params = {"q": "%", "scope": "all", "hotel": "sandbox"}
    assert api.get("/api/catalog/items", params=params).json()["total"] == 0


def test_hotel_outside_the_list_is_refused(api: Api, habbo: FakeHabbo) -> None:
    res = api.post("/api/catalog/sync", json={"hotel": "evil.example"})
    assert res.status_code == 422
    assert habbo.requests == []


def test_redirects_may_not_leave_the_host_list(api: Api, habbo: FakeHabbo) -> None:
    for location in (
        "https://evil.example/x",
        "http://sandbox.habbo.com/x",
        "https://sandbox.habbo.com.evil.example/x",
        "https://169.254.169.254/latest/meta-data",
    ):
        habbo.status, habbo.status_headers = 307, {"location": location}
        before = len(habbo.requests)
        res = api.post("/api/catalog/sync", json={"hotel": "sandbox", "force": True})
        assert res.status_code == 502, location
        assert len(habbo.requests) == before + 1, "the refused hop was never requested"
        assert "not changed" in res.json()["message"]


def test_redirect_loops_stop(api: Api, habbo: FakeHabbo) -> None:
    habbo.status, habbo.status_headers = 307, {"location": "/gamedata/furnidata_json/again"}
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"})
    assert res.status_code == 502
    assert "redirects" in res.json()["message"]
    assert len(habbo.requests) == 4


@pytest.mark.parametrize(
    "origin,expected",
    [
        ("http://localhost:8000", True),
        ("http://127.0.0.1:8000", True),
        ("http://127.0.0.1:9000", False),
        ("https://127.0.0.1:8000", False),
        ("http://evil.example:8000", False),
    ],
)
def test_loopback_origins(origin: str, expected: bool) -> None:
    assert same_origin(origin, "http://127.0.0.1:8000") is expected


def test_login_throttle(client: TestClient) -> None:
    for _ in range(5):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert res.status_code == 401
    res = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


def test_write_rate_limit(tmp_path: Path, settings: Settings, habbo: FakeHabbo) -> None:
    settings.rate_limit_writes = 3
    app = create_app(settings, transport=httpx.MockTransport(habbo))
    with TestClient(app, base_url="http://testserver") as client:
        api = Api(client)  # The login is the first write.
        statuses = [api.post("/api/folders", json={"name": f"f{i}"}).status_code for i in range(4)]
    assert statuses == [201, 201, 429, 429]


def test_run_ticks_have_their_own_budget(settings: Settings, habbo: FakeHabbo) -> None:
    settings.rate_limit_writes = 4
    settings.rate_limit_ticks = 3
    app = create_app(settings, transport=httpx.MockTransport(habbo))
    with TestClient(app, base_url="http://testserver") as client:
        api = Api(client)  # The login is the first write.
        room = api.post("/api/sandboxes", json={"name": "room"}).json()["id"]
        assert api.post(f"/api/sandboxes/{room}/run", json={"seed": 1}).status_code == 201
        ticks = [
            api.post(f"/api/sandboxes/{room}/run/advance", json={"ms": 250}).status_code for _ in range(4)
        ]
        assert ticks == [200, 200, 200, 429]
        assert api.post("/api/folders", json={"name": "still allowed"}).status_code == 201
        assert api.post("/api/folders", json={"name": "over"}).status_code == 429


def test_read_rate_limit(settings: Settings, habbo: FakeHabbo) -> None:
    settings.rate_limit_reads = 2
    app = create_app(settings, transport=httpx.MockTransport(habbo))
    with TestClient(app, base_url="http://testserver") as client:
        assert [client.get("/healthz").status_code for _ in range(3)] == [200, 200, 429]


def test_rate_limiter_window_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr("wiredbench.security.time.monotonic", lambda: now[0])
    limiter = RateLimiter(1, 10)
    assert limiter.hit("a") == 0
    assert limiter.hit("a") > 0
    assert limiter.hit("b") == 0
    now[0] += 11
    assert limiter.hit("a") == 0
