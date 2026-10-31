"""Spike contract tests: live-observed behaviour, official spec shapes, spec coverage.

Set WB_OPENAPI_SPEC to a saved copy of the official spec (extracted from swagger-ui-init.js).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from mock_api import Room, create_app

R, W = {"X-Wired-Read-Key": "r"}, {"X-Wired-Write-Key": "w"}
BOTH = {**R, **W}
ROOM = "/api/public/rooms/1"
SPEC = json.loads(Path(os.environ["WB_OPENAPI_SPEC"]).read_text())


@pytest.fixture
def client() -> TestClient:
    room = Room("r", "w", definitions={"user": {"troll", "score"}, "furni": {"state"}, "global": {"clock"}})
    room.users["44"] = {"id": 44, "name": "SomeName", "unique_id": "hhus-abc"}
    return TestClient(create_app({1: room}))


def schema(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]}


def conforms(body, name: str) -> None:
    jsonschema.validate(body, schema(name))


def error(res, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    assert res.json() == {"error": code}


def give(client: TestClient, value="5", name="troll", path="user/{}/users/44") -> dict:
    res = client.put(f"{ROOM}/variables/{path.format(name)}", headers=W, json={"value": value})
    assert res.status_code == 200, res.text
    return res.json()


# --- Behaviour seen on a real room (habbo-wired-api openapi-spec.md, section 1b) ---


def test_read_key_alone_reads(client):
    res = client.get(f"{ROOM}/variables", headers=R)
    assert res.status_code == 200
    conforms(res.json(), "WiredRoomVariables")


@pytest.mark.parametrize("headers", [{}, {"X-Wired-Read-Key": "bad"}, W])
def test_missing_or_wrong_read_key(client, headers):
    error(client.get(f"{ROOM}/variables", headers=headers), 403, "wired.variables.key_invalid")


def test_read_key_cannot_write(client):
    give(client)
    res = client.patch(f"{ROOM}/variables/user/troll/users/44", headers=R, json={"value": "1"})
    error(res, 403, "wired.variables.key_invalid")


def test_unknown_variable(client):
    error(client.get(f"{ROOM}/variables/global/nope", headers=R), 404, "wired.variables.not_found")
    error(client.get(f"{ROOM}/variables/user/nope/users", headers=R), 404, "wired.variables.not_found")


def test_no_profile(client):
    error(client.get(f"{ROOM}/variables_profile/user/users?name=SomeName", headers=R), 404, "wired.variables.entity_not_found")


def test_bad_target_and_entity(client):
    error(client.get(f"{ROOM}/variables/user/troll/badkind", headers=R), 400, "wired.variables.invalid_target")
    error(client.get(f"{ROOM}/variables/user/troll/users/abc", headers=R), 404, "not-found")


def test_room_without_addon_is_generic_404():
    # Also seen on sandbox.habbo.com with and without a key (2026-10-31).
    client = TestClient(create_app({}))
    for headers in ({}, {"X-Wired-Read-Key": "bad"}):
        error(client.get(f"{ROOM}/variables", headers=headers), 404, "not-found")


def test_page_rules(client):
    give(client)
    res = client.get(f"{ROOM}/variables/user/troll/users?size=101", headers=R)
    assert res.json()["size"] == 100
    conforms(res.json(), "WiredPagedVariables")
    error(client.get(f"{ROOM}/variables/user/troll/users?page=0", headers=R), 400, "wired.variables.invalid_target")


def test_paged_item_shape_and_count(client):
    give(client)
    res = client.get(f"{ROOM}/variables/user/troll/users?size=3&order_by=update_time&order_dir=desc", headers=R)
    item = res.json()["items"][0]
    assert set(item) == {"variable", "user"}
    assert item["user"] == {"id": 44, "name": "SomeName", "unique_id": "hhus-abc"}
    assert client.get(f"{ROOM}/variables/user/troll/users/count", headers=R).json() == {"count": 1}


def test_etag_revalidation(client):
    first = client.get(f"{ROOM}/variables", headers=R)
    again = client.get(f"{ROOM}/variables", headers={**R, "If-None-Match": first.headers["etag"]})
    assert first.headers["etag"].startswith('W/"')
    assert again.status_code == 304 and again.content == b""


def test_string_and_number_values_return_strings(client):
    give(client)
    for raw, expected in (("5", "5"), (6, "6")):
        res = client.patch(f"{ROOM}/variables/user/troll/users/44", headers=W, json={"value": raw})
        assert res.json()["value"] == expected
        conforms(res.json(), "WiredVariable")


def test_int64_edges(client):
    give(client)
    url = f"{ROOM}/variables/user/troll/users/44"
    big = str(2**63 - 1)
    assert client.patch(url, headers=W, json={"value": big}).json()["value"] == big
    assert client.patch(url, headers=W, json={"value": str(2**63)}).status_code == 400


def test_same_value_write_bumps_update_time(client):
    first = give(client)
    import time

    time.sleep(0.005)
    second = client.patch(f"{ROOM}/variables/user/troll/users/44", headers=W, json={"value": "5"}).json()
    assert second["update_time"] != first["update_time"]
    assert second["creation_time"] == first["creation_time"]


def test_batch_keys_and_results(client):
    give(client, "1")
    body = {"requests": [
        {"op_id": "get-me", "method": "GET", "path": "users/44"},
        {"op_id": "set-me", "method": "PATCH", "path": "users/44", "body": {"value": "9"}},
        {"op_id": "bad", "method": "GET", "path": "nope/1"},
        {"op_id": "gone", "method": "DELETE", "path": "users/44"},
    ]}
    url = f"{ROOM}/variables/user/troll/batch"
    error(client.post(url, headers=W, json=body), 403, "wired.variables.key_missing")
    results = client.post(url, headers=BOTH, json=body).json()["results"]
    assert results[0]["body"]["value"] == "1" and results[0]["error"] is None  # In order; old value first.
    assert results[1]["body"]["value"] == "9"
    assert results[2]["status"] == 400 and results[2]["error"]["code"] == "wired.variables.invalid_target"
    assert results[3]["status"] == 204


def test_batch_size_limit(client):
    url = f"{ROOM}/variables/user/troll/batch"
    assert client.post(url, headers=BOTH, json={"requests": []}).status_code == 400
    ops = [{"method": "GET", "path": "users/44"}] * 51
    assert client.post(url, headers=BOTH, json={"requests": ops}).status_code == 400


def test_profiles(client):
    give(client)
    # Live: name lookup is case-insensitive; all three lookups give the same body.
    by_name = client.get(f"{ROOM}/variables_profile/user/users?name=SOMENAME", headers=R)
    by_uid = client.get(f"{ROOM}/variables_profile/user/users?unique_id=hhus-abc", headers=R)
    by_id = client.get(f"{ROOM}/variables_profile/user/users/44", headers=R)
    assert by_name.json() == by_uid.json() == by_id.json()
    conforms(by_name.json(), "WiredUserProfile")

    patched = client.patch(f"{ROOM}/variables_profile/user/users/44", headers=W, json={"variables": {"score": "7", "troll": None}})
    assert set(patched.json()["variables"]) == {"score"}
    assert client.delete(f"{ROOM}/variables_profile/user/users/44", headers=W).status_code == 204
    error(client.get(f"{ROOM}/variables_profile/user/users/44", headers=R), 404, "wired.variables.entity_not_found")


def test_furni_and_global_profiles(client):
    give(client, name="state", path="furni/{}/furni/9")
    res = client.get(f"{ROOM}/variables_profile/furni/furni/9", headers=R)
    conforms(res.json(), "WiredFurniProfile")
    assert client.patch(f"{ROOM}/variables/global/clock", headers=W, json={"value": "3"}).json()["value"] == "3"
    profile = client.get(f"{ROOM}/variables_profile/global", headers=R)
    conforms(profile.json(), "WiredGlobalProfile")


def test_bulk_delete_is_refused_by_default(client):
    res = client.post(f"{ROOM}/variables/bulk-delete", headers=W, json={"variables": ["troll"]})
    assert res.status_code == 403


# --- Coverage of the official spec ---


def test_every_wired_operation_in_the_spec_is_routed():
    app = create_app({})
    routed = []
    for route in app.routes:
        if hasattr(route, "methods") and route.path.startswith("/api/public/rooms/"):
            for method in route.methods:
                routed.append((method.lower(), re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", route.path) + "$")))

    missing = []
    total = 0
    for path, operations in SPEC["paths"].items():
        if "/variables" not in path:
            continue
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        for method in operations:
            total += 1
            if not any(m == method and rx.match(concrete) for m, rx in routed):
                missing.append(f"{method} {path}")
    assert total > 0
    assert missing == []
