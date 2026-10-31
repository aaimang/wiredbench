"""The mock Web API, against behaviour recorded from real rooms and the official spec's shapes."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import Api
from wiredbench.api import mock
from wiredbench.engine.core import replay
from wiredbench.engine.tutorials import AVATAR

SPEC_PATH = os.environ.get("WB_OPENAPI_SPEC")


def box(furni_id: int, classname: str, variable: str, x: int) -> dict[str, Any]:
    return {"id": furni_id, "classname": classname, "x": x, "y": 9, "z": 0, "wired": {"variable": variable}}


class Room:
    def __init__(self, api: Api) -> None:
        self.api = api
        res = api.post("/api/tutorials/time-tracking", json={})
        self.id = res.json()["id"]
        document = api.get(f"/api/sandboxes/{self.id}").json()["document"]
        document["furni"] += [
            box(901, "wf_var_user", "troll", 1),
            box(902, "wf_var_furni", "shine", 2),
            box(903, "wf_var_room", "clock", 3),
        ]
        saved = api.put(f"/api/sandboxes/{self.id}/document", json={"document": document, "base_revision": 2})
        assert saved.status_code == 200, saved.text
        self.url = f"/api/public/rooms/{self.id}"
        keys = api.post(f"/api/sandboxes/{self.id}/api-keys", json={}).json()
        self.read = {"X-Wired-Read-Key": keys["read_key"]}
        self.write = {"X-Wired-Write-Key": keys["write_key"]}
        assert api.post(f"/api/sandboxes/{self.id}/run", json={"seed": 1}).status_code == 201

    def get(self, path: str, headers: dict[str, str] | None = None, **kwargs: Any) -> Any:
        return self.api.client.get(
            self.url + path, headers=self.read if headers is None else headers, **kwargs
        )

    def send(self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
        return self.api.client.request(
            method, self.url + path, headers=self.write if headers is None else headers, json=body
        )

    def give(self, value: Any = "5", path: str = "/variables/user/troll/users/44") -> dict[str, str]:
        res = self.send("PUT", path, {"value": value})
        assert res.status_code == 200, res.text
        return res.json()


@pytest.fixture
def room(api: Api) -> Room:
    return Room(api)


def error(res: Any, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    assert res.json() == {"error": code}


def test_definitions_come_from_the_variable_boxes(room: Room) -> None:
    body = room.get("/variables").json()
    assert "troll" in body["users"]
    assert body["furni"] == ["shine"]
    assert body["global"] == ["clock"]


@pytest.mark.parametrize("key", [None, {"X-Wired-Read-Key": "bad"}])
def test_missing_or_wrong_read_key(room: Room, key: dict[str, str] | None) -> None:
    error(room.get("/variables", headers=key or {}), 403, "wired.variables.key_invalid")


def test_keys_do_not_cross(room: Room) -> None:
    error(room.get("/variables", headers=room.write), 403, "wired.variables.key_invalid")
    res = room.send("PUT", "/variables/user/troll/users/44", {"value": 1}, headers=room.read)
    error(res, 403, "wired.variables.key_invalid")


def test_the_login_cookie_is_not_a_key(room: Room) -> None:
    error(room.get("/variables", headers={}), 403, "wired.variables.key_invalid")


def test_a_room_with_no_saved_keys_says_so(api: Api, room: Room) -> None:
    assert api.delete(f"/api/sandboxes/{room.id}/api-keys").status_code == 204
    error(room.get("/variables"), 403, "wired.variables.key_missing")
    assert api.get(f"/api/sandboxes/{room.id}/api-keys").json()["configured"] is False


def test_a_room_that_is_not_running_looks_absent(api: Api, room: Room) -> None:
    api.delete(f"/api/sandboxes/{room.id}/run")
    error(room.get("/variables"), 404, "not-found")
    error(api.client.get("/api/public/rooms/99999/variables"), 404, "not-found")
    error(api.client.get("/api/public/rooms/abc/variables"), 404, "not-found")


def test_order_of_failures_matches_live(api: Api, room: Room) -> None:
    error(
        api.client.get("/api/public/rooms/99999/variables/user/x/nothing"),
        400,
        "wired.variables.invalid_target",
    )
    assert room.get("/variables/nothing/x/users").status_code == 404
    assert room.get("/variables/nothing/x/users").content == b""
    error(room.get("/variables_profile/user/users/abc", headers={}), 404, "not-found")
    error(room.get("/variables/user/troll/users/abc", headers={}), 404, "not-found")


def test_unknown_variable_and_profile(room: Room) -> None:
    error(room.get("/variables/global/nope"), 404, "wired.variables.not_found")
    error(room.get("/variables/user/nope/users"), 404, "wired.variables.not_found")
    error(room.get("/variables_profile/user/users/44"), 404, "wired.variables.entity_not_found")
    res = room.get("/variables_profile/user/users", params={"name": "nobody"})
    error(res, 404, "wired.variables.entity_not_found")


def test_values_are_text_and_both_forms_are_accepted(room: Room) -> None:
    assert room.give("5")["value"] == "5"
    assert room.give(6)["value"] == "6"
    assert room.give(str(2**63 - 1))["value"] == str(2**63 - 1)
    assert set(room.give(1)) == {"value", "creation_time", "update_time"}
    for bad in (str(2**63), "abc", 1.5, True, None):
        res = room.send("PUT", "/variables/user/troll/users/44", {"value": bad})
        assert res.status_code == 400, bad


def test_writes_reach_the_running_room(api: Api, room: Room) -> None:
    room.give(7, "/variables/user/troll/users/1")
    state = api.get(f"/api/sandboxes/{room.id}/run").json()
    rows = [r for r in state["variables"] if r["variable"] == "troll"]
    assert rows[0]["holder"] == "user:1"
    assert rows[0]["value"] == "7"
    api.post(f"/api/sandboxes/{room.id}/run/command", json={"text": ":set user Worker troll 9"})
    assert room.get(f"/variables/user/troll/users/{AVATAR}").json()["value"] == "9"


def test_same_value_write_still_moves_update_time(api: Api, room: Room) -> None:
    first = room.give(1)
    api.post(f"/api/sandboxes/{room.id}/run/advance", json={"ms": 1000})
    second = room.give(1)
    assert second["creation_time"] == first["creation_time"]
    assert second["update_time"] > first["update_time"]


def test_undefined_variables_cannot_be_written(room: Room) -> None:
    res = room.send("PUT", "/variables/user/nope/users/44", {"value": 1})
    error(res, 404, "wired.variables.not_found")
    error(room.send("PATCH", "/variables/global/nope", {"value": 1}), 404, "wired.variables.not_found")
    error(
        room.send("PATCH", "/variables/user/troll/users/44", {"value": 1}), 404, "wired.variables.not_found"
    )


def test_pages_and_counts(room: Room) -> None:
    for number, value in ((1, 30), (2, 10), (3, 20)):
        room.give(value, f"/variables/user/troll/users/{number}")
    assert room.get("/variables/user/troll/users/count").json() == {"count": 3}
    assert room.get("/variables/user/troll/pets/count").json() == {"count": 0}
    body = room.get("/variables/user/troll/users", params={"order_dir": "desc", "size": 2}).json()
    assert [row["variable"]["value"] for row in body["items"]] == ["30", "20"]
    assert (body["page"], body["size"]) == (1, 2)
    assert set(body["items"][0]["user"]) == {"id", "name", "unique_id"}, (
        "the official wrapper reads all three"
    )
    limited = room.get("/variables/user/troll/users", params={"size": 1000}).json()
    assert limited["size"] == 100
    error(room.get("/variables/user/troll/users", params={"page": 0}), 400, "wired.variables.invalid_target")


def test_etag_revalidation(room: Room) -> None:
    first = room.get("/variables")
    assert first.headers["etag"].startswith('W/"')
    second = room.get("/variables", headers={**room.read, "If-None-Match": first.headers["etag"]})
    assert second.status_code == 304


def test_errors_carry_an_etag_like_a_real_room(room: Room) -> None:
    res = room.get("/variables/global/nope")
    error(res, 404, "wired.variables.not_found")
    assert res.headers["etag"].startswith('W/"')
    assert "etag" not in room.get("/variables/nothing/x/users").headers, "the empty 404 has none"
    write = room.send("PATCH", "/variables/global/nope", {"value": 1})
    assert write.status_code == 404
    assert write.headers["etag"].startswith('W/"')


def test_successful_writes_carry_an_etag_like_a_real_room(room: Room) -> None:
    res = room.send("PATCH", "/variables/global/clock", {"value": 3})
    assert res.status_code == 200
    assert res.headers["etag"].startswith('W/"')
    assert res.json()["value"] == "3"
    assert room.send("PUT", "/variables/user/troll/users/44", {"value": 1}).headers["etag"]


def test_value_errors_match_a_real_room(room: Room) -> None:
    path = "/variables/global/clock"
    for bad in ("abc", 1.5, True, str(2**63)):
        error(room.send("PATCH", path, {"value": bad}), 400, "request-failed-non-200")
    error(room.send("PATCH", path, {"value": None}), 400, "wired.variables.invalid_value")
    error(room.send("PATCH", path, {}), 400, "wired.variables.invalid_value")
    # A bad value is reported first, and a good one then finds the variable missing.
    missing = "/variables/global/nope"
    error(room.send("PATCH", missing, {"value": "abc"}), 400, "request-failed-non-200")
    error(room.send("PATCH", missing, {"value": 1}), 404, "wired.variables.not_found")


def test_bad_order_is_refused_like_a_real_room(room: Room) -> None:
    res = room.get("/variables/user/troll/users", params={"order_by": "nonsense"})
    error(res, 400, "wired.variables.invalid_target")


def test_empty_bulk_delete_is_refused_first_like_a_real_room(room: Room) -> None:
    res = room.send("POST", "/variables/bulk-delete", {"variables": []})
    error(res, 400, "wired.variables.bulk_delete_empty")


def test_global_variables_have_no_batch_route_like_a_real_room(room: Room) -> None:
    both = {**room.read, **room.write}
    for headers in (room.read, both):
        res = room.send("POST", "/variables/global/clock/batch", {"requests": []}, headers=headers)
        assert res.status_code == 404
        assert res.content == b""


def test_delete_and_profiles(room: Room) -> None:
    room.give(5, f"/variables/user/troll/users/{AVATAR}")
    profile = room.get(f"/variables_profile/user/users/{AVATAR}").json()
    assert profile["user"]["name"] == "Worker"
    assert profile["variables"]["troll"]["value"] == "5"
    found = room.get("/variables_profile/user/users", params={"name": "worker"}).json()
    assert found["user"]["id"] == AVATAR
    by_id = room.get("/variables_profile/user/users", params={"unique_id": profile["user"]["unique_id"]})
    assert by_id.status_code == 200
    patched = room.send(
        "PATCH", f"/variables_profile/user/users/{AVATAR}", {"variables": {"troll": 8}}
    ).json()
    assert patched["variables"]["troll"]["value"] == "8"
    assert room.send("DELETE", f"/variables/user/troll/users/{AVATAR}").status_code == 204
    res = room.send("DELETE", f"/variables/user/troll/users/{AVATAR}")
    error(res, 404, "wired.variables.not_found")


def test_furni_and_global_profiles(room: Room) -> None:
    room.give(4, "/variables/furni/shine/furni/901")
    assert room.get("/variables_profile/furni/furni/901").json()["furni"] == {"id": 901}
    assert room.send("PATCH", "/variables/global/clock", {"value": 3}).json()["value"] == "3"
    assert room.get("/variables/global/clock").json()["value"] == "3"
    assert room.get("/variables_profile/global").json()["variables"]["clock"]["value"] == "3"
    body = room.send("PATCH", "/variables_profile/global", {"variables": {"clock": "4"}}).json()
    assert body["variables"]["clock"]["value"] == "4"


def test_batch_keeps_the_live_format(room: Room) -> None:
    both = {**room.read, **room.write}
    path = "/variables/user/troll/batch"
    one = [{"method": "GET", "path": "users/1"}]
    error(room.send("POST", path, {"requests": one}), 403, "wired.variables.key_missing")
    for headers in (room.read, room.write, both):
        error(room.send("POST", path, {"requests": []}, headers=headers), 400, "wired.variables.batch_empty")
    too_many = [{"method": "GET", "path": "users/1"}] * 51
    assert room.send("POST", path, {"requests": too_many}, headers=both).status_code == 400
    operations = [
        {"op_id": "a", "method": "PUT", "path": "users/44", "body": {"value": 2}},
        {"op_id": "b", "method": "GET", "path": "users/44"},
        {"op_id": "c", "method": "DELETE", "path": "users/44"},
        {"op_id": "d", "method": "GET", "path": "users/44"},
    ]
    results = room.send("POST", path, {"requests": operations}, headers=both).json()["results"]
    assert [r["status"] for r in results] == [200, 200, 204, 404]
    assert results[0]["error"] is None, "a real room sends error: null on success"
    assert results[3]["error"]["code"] == "wired.variables.not_found"


def test_bulk_delete_needs_the_option(api: Api, room: Room) -> None:
    room.give(1)
    res = room.send("POST", "/variables/bulk-delete", {"variables": ["troll"]})
    error(res, 403, "wired.variables.key_invalid")
    keys = api.post(f"/api/sandboxes/{room.id}/api-keys", json={"allow_mass_deletion": True}).json()
    write = {"X-Wired-Write-Key": keys["write_key"]}
    assert (
        room.send("POST", "/variables/bulk-delete", {"variables": ["troll"]}, headers=write).status_code
        == 204
    )
    assert room.get(
        "/variables/user/troll/users/count", headers={"X-Wired-Read-Key": keys["read_key"]}
    ).json() == {"count": 0}


def test_keys_are_stored_hashed_and_replaced(api: Api, room: Room) -> None:
    old = room.read
    status = api.get(f"/api/sandboxes/{room.id}/api-keys").json()
    assert status["configured"] is True
    assert "read_key" not in status
    api.post(f"/api/sandboxes/{room.id}/api-keys", json={})
    error(room.get("/variables", headers=old), 403, "wired.variables.key_invalid")


def test_bad_json_is_refused(api: Api, room: Room) -> None:
    res = api.client.put(
        f"{room.url}/variables/user/troll/users/44", headers=room.write, content=b"{not json"
    )
    assert res.status_code == 400


def test_api_writes_replay(api: Api, room: Room) -> None:
    """API and debug writes are inputs, so a run with them can be rebuilt exactly."""
    room.give(5, f"/variables/user/troll/users/{AVATAR}")
    api.post(f"/api/sandboxes/{room.id}/run/command", json={"text": ":set global x clock 3"})
    services = api.client.app.state.services  # type: ignore[attr-defined]
    run = services.runs.get(room.id)
    document = api.get(f"/api/sandboxes/{room.id}").json()["document"]
    rebuilt = replay(document, run.engine.seed, run.engine.inputs, run.engine.now_ms)
    assert rebuilt.view_variables() == run.engine.view_variables()


@pytest.mark.skipif(not SPEC_PATH, reason="Set WB_OPENAPI_SPEC to a saved copy of the official spec.")
def test_every_wired_operation_in_the_spec_is_routed() -> None:
    spec = json.loads(Path(SPEC_PATH or "").read_text())
    routed = [
        (method.lower(), re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", route.path) + "$"))
        for route in mock.router.routes
        for method in route.methods  # type: ignore[attr-defined]
    ]
    wired = [(path, method) for path, ops in spec["paths"].items() if "/variables" in path for method in ops]
    assert len(wired) >= 18
    missing = [
        f"{method} {path}"
        for path, method in wired
        if not any(m == method and rx.match(re.sub(r"\{[^}]+\}", "1", path)) for m, rx in routed)
    ]
    assert missing == []
