"""View as normal user is enforced on the server, so these walk every route and read every answer."""

from __future__ import annotations

import json

from fastapi.routing import APIRoute

from conftest import Api, FakeHabbo, apply_update, furni, furnidata
from wiredbench.api import ROUTERS

ALLOWED = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("DELETE", "/api/auth/view-as"),
    ("GET", "/api/settings"),
    ("GET", "/api/view/sandboxes"),
    ("GET", "/api/view/sandboxes/{sandbox_id}"),
    ("POST", "/api/view/sandboxes/{sandbox_id}/run"),
    ("POST", "/api/view/sandboxes/{sandbox_id}/run/advance"),
    ("POST", "/api/view/sandboxes/{sandbox_id}/run/input"),
    ("GET", "/api/furni/{revision}/{classname}/manifest"),
    ("GET", "/api/furni/{revision}/{classname}/atlas"),
    ("GET", "/api/avatars/{hotel}/lookup"),
    ("GET", "/api/avatars/{hotel}/image"),
}
SECRET = "secret-variable-name"


def room_with_secrets(api: Api) -> int:
    room = api.post("/api/tutorials/time-tracking", json={}).json()["id"]
    document = api.get(f"/api/sandboxes/{room}").json()["document"]
    document["furni"] += [
        {"id": 901, "classname": "wf_var_room", "x": 1, "y": 9, "z": 0, "wired": {"variable": SECRET}},
        {"id": 902, "classname": "wf_trg_staff_only", "x": 2, "y": 9, "z": 0, "note": SECRET},
    ]
    res = api.put(f"/api/sandboxes/{room}/document", json={"document": document, "base_revision": 2})
    assert res.status_code == 200, res.text
    return room


def test_a_view_session_reaches_only_the_allowed_routes(api: Api) -> None:
    room_with_secrets(api)
    me = api.post("/api/auth/view-as").json()
    assert me["view_as"] is True
    checked = 0
    for router in ROUTERS:
        for route in router.routes:
            assert isinstance(route, APIRoute)
            if getattr(route.endpoint, "__wb_public__", False):
                continue
            for method in route.methods - {"HEAD"}:
                if (method, route.path) in ALLOWED:
                    assert getattr(route.endpoint, "__wb_viewer__", False)
                    continue
                checked += 1
                path = route.path.replace("{kind}", "folder").replace("{classname}", "chair")
                path = path.replace("{sandbox_id}", "1").replace("{revision}", "1")
                for name in ("folder_id", "item_id", "version_id", "from_id", "to_id", "hotel"):
                    path = path.replace("{" + name + "}", "1")
                res = api._send(method, path, json={})
                assert res.status_code == 403, f"{method} {route.path}: {res.status_code}"
                assert res.json()["error"] == "view_as"
    assert checked > 30, "this walk must keep checking real routes"


def test_view_routes_never_send_config(api: Api, habbo: FakeHabbo) -> None:
    habbo.set(furnidata(furni("wf_trg_staff_only", offerid=-1, bc=False)), 'W/"v2"')
    apply_update(api)
    room = room_with_secrets(api)
    api.post(f"/api/sandboxes/{room}/run", json={"seed": 1})
    api.post(f"/api/sandboxes/{room}/run/command", json={"text": f":set global x {SECRET} 3"})
    api.post("/api/auth/view-as")

    answers = [
        api.get(f"/api/view/sandboxes/{room}"),
        api.post(f"/api/view/sandboxes/{room}/run"),
        api.post(f"/api/view/sandboxes/{room}/run/advance", json={"ms": 500}),
        api.post(f"/api/view/sandboxes/{room}/run/input", json={"type": "say", "user": 1, "text": "hi"}),
    ]
    for res in answers:
        assert res.status_code in (200, 201), res.text
        text = json.dumps(res.json())
        assert SECRET not in text
        for word in ("wired", "trace", "variables", "seed", "limit_hits", "metrics"):
            assert f'"{word}"' not in text
    document = answers[0].json()["document"]
    assert 902 not in {item["id"] for item in document["furni"]}, "unknown and staff boxes stay hidden"
    assert 902 not in {item["id"] for item in answers[1].json()["furni"]}
    assert (
        api.post(
            f"/api/view/sandboxes/{room}/run/input", json={"type": "use", "user": 1, "furni": 902}
        ).status_code
        == 404
    )


def test_view_input_cannot_use_debug_or_api_writes(api: Api) -> None:
    room = room_with_secrets(api)
    api.post("/api/auth/view-as")
    api.post(f"/api/view/sandboxes/{room}/run")
    for kind in ("debug_set", "api_set", "enter", "leave"):
        body = {"type": kind, "user": 1, "variable": "x", "key": "global", "value": 1}
        assert api.post(f"/api/view/sandboxes/{room}/run/input", json=body).status_code == 422


def test_leaving_view_as_restores_admin(api: Api) -> None:
    api.post("/api/auth/view-as")
    assert api.get("/api/workspace/tree").status_code == 403
    assert api.get("/api/auth/me").json()["view_as"] is True
    assert api.delete("/api/auth/view-as").json()["view_as"] is False
    assert api.get("/api/workspace/tree").status_code == 200
    actions = [row["action"] for row in api.get("/api/audit").json()]
    assert "view_as_start" in actions
    assert "view_as_stop" in actions


def test_another_login_is_not_in_view_mode(api: Api) -> None:
    api.post("/api/auth/view-as")
    assert api.get("/api/catalog/status", params={"hotel": "sandbox"}).status_code == 403


def test_dashboard_counts_a_run(api: Api) -> None:
    assert api.get("/api/dashboard").json() == {"rooms": []}
    room = api.post("/api/tutorials/time-tracking", json={}).json()["id"]
    api.post(f"/api/sandboxes/{room}/run", json={"seed": 1})
    api.post(f"/api/sandboxes/{room}/run/input", json={"type": "move", "user": 1, "x": 4, "y": 4})
    api.post(f"/api/sandboxes/{room}/run/advance", json={"ms": 3000})
    only = api.get("/api/dashboard").json()["rooms"][0]
    assert only["id"] == room
    assert only["name"] == "Time tracking example"
    assert {"boxes", "stacks", "signals", "errors", "stubs", "limit_hits", "problems"} <= set(only)
    assert all(row["runs"] > 0 for row in only["boxes"])


def test_settings_change_tick_rate_and_mock_limit(api: Api) -> None:
    saved = api.patch("/api/settings", json={"tick_ms": 250, "rate_limit_mock": 2, "audit_days": 30}).json()
    assert (saved["tick_ms"], saved["rate_limit_mock"], saved["audit_days"]) == (250, 2, 30)
    assert api.patch("/api/settings", json={"tick_ms": 1}).status_code == 422
    room = api.post("/api/tutorials/time-tracking", json={}).json()["id"]
    api.post(f"/api/sandboxes/{room}/run", json={"seed": 1})
    services = api.client.app.state.services  # type: ignore[attr-defined]
    assert services.runs.get(room).engine.tick_ms == 250
    url = f"/api/public/rooms/{room}/variables"
    codes = [api.client.get(url).status_code for _ in range(3)]
    assert codes[-1] == 429
