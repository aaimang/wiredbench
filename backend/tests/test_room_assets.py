from __future__ import annotations

from pathlib import Path

import pytest

from conftest import PNG, Api, FakeHabbo, apply_update, furni, furnidata
from swf_builder import furni_swf
from wiredbench.services.assets import AssetCache

FIGURE = "hd-180-1.ch-210-66.lg-270-82"


@pytest.fixture
def box(api: Api, habbo: FakeHabbo) -> Api:
    habbo.set(furnidata(furni("box"), furni("chair_plasto*1"), furni("broken"), furni("gone")), 'W/"v1"')
    apply_update(api)
    habbo.files |= {
        "box.swf": furni_swf("box"),
        "chair_plasto.swf": furni_swf("chair_plasto"),
        "broken.swf": b"junk",
    }
    return api


def test_furni_is_built_once_and_cached(box: Api, habbo: FakeHabbo) -> None:
    manifest = box.get("/api/furni/100/box/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["directions"] == [2, 4]
    assert "immutable" in manifest.headers["cache-control"]
    count = len(habbo.requests)
    atlas = box.get("/api/furni/100/box/atlas")
    assert atlas.headers["content-type"] == "image/png"
    assert atlas.content.startswith(PNG[:8])
    assert len(habbo.requests) == count


def test_colour_variants_share_the_base_file(box: Api, habbo: FakeHabbo) -> None:
    assert box.get("/api/furni/100/chair_plasto*1/manifest").status_code == 200
    assert any(r.url.path.endswith("/chair_plasto.swf") for r in habbo.requests)


def test_missing_and_damaged_furni_are_remembered(box: Api, habbo: FakeHabbo) -> None:
    for name in ("gone", "broken"):
        assert box.get(f"/api/furni/100/{name}/manifest").status_code == 404
        count = len(habbo.requests)
        assert box.get(f"/api/furni/100/{name}/atlas").status_code == 404
        assert len(habbo.requests) == count


def test_only_catalogue_furni_reach_habbo(box: Api, habbo: FakeHabbo) -> None:
    count = len(habbo.requests)
    for url in (
        "/api/furni/100/not_listed/manifest",
        "/api/furni/999/box/atlas",
        "/api/furni/100/..%2f..%2fx/atlas",
    ):
        assert box.get(url).status_code == 404
    assert len(habbo.requests) == count


def test_upstream_failure_is_clear_and_retried(box: Api, habbo: FakeHabbo) -> None:
    habbo.fail = True
    assert box.get("/api/furni/100/box/manifest").status_code == 502
    habbo.fail = False
    assert box.get("/api/furni/100/box/manifest").status_code == 200


def test_avatar_frames_are_cached(api: Api, habbo: FakeHabbo) -> None:
    params = {"figure": FIGURE, "action": "wlk", "direction": 3, "frame": 2}
    res = api.get("/api/avatars/com/image", params=params)
    assert res.status_code == 200
    assert res.content == PNG
    sent = habbo.requests[-1]
    assert sent.url.host == "www.habbo.com"
    assert sent.url.params["action"] == "wlk"
    assert sent.url.params["head_direction"] == "3"
    count = len(habbo.requests)
    assert api.get("/api/avatars/com/image", params=params).status_code == 200
    assert len(habbo.requests) == count
    assert api.get("/api/cache").json()["assets_bytes"] == len(PNG), "counts toward the cache limit"
    assert api.post("/api/cache/clear").json()["removed"] == 1


@pytest.mark.parametrize(
    "params",
    [
        {"figure": "../../etc/passwd"},
        {"figure": "hd-180&user=x"},
        {"figure": FIGURE, "action": "evil"},
        {"figure": FIGURE, "gesture": "evil"},
        {"figure": FIGURE, "direction": 8},
        {"figure": FIGURE, "frame": 4},
        {"figure": "hd-1." * 200},
    ],
)
def test_bad_avatar_values_never_reach_habbo(api: Api, habbo: FakeHabbo, params: dict) -> None:
    assert api.get("/api/avatars/com/image", params=params).status_code == 422
    assert habbo.requests == []


def test_avatar_image_that_is_not_png_is_refused(api: Api, habbo: FakeHabbo) -> None:
    habbo.avatar = b"<html>blocked</html>"
    assert api.get("/api/avatars/com/image", params={"figure": FIGURE}).status_code == 502


def test_name_lookup(api: Api, habbo: FakeHabbo) -> None:
    habbo.profiles["Someone"] = {"name": "Someone", "figureString": FIGURE}
    res = api.get("/api/avatars/de/lookup", params={"name": "Someone"})
    assert res.json() == {"name": "Someone", "figure": FIGURE}
    assert habbo.requests[-1].url.host == "www.habbo.de"
    assert api.get("/api/avatars/de/lookup", params={"name": "Ghost"}).status_code == 404
    assert api.get("/api/avatars/evil/lookup", params={"name": "Someone"}).status_code == 422
    count = len(habbo.requests)
    assert api.get("/api/avatars/de/lookup", params={"name": "a b/c"}).status_code == 422
    assert len(habbo.requests) == count


def test_lookup_refuses_a_hostile_profile(api: Api, habbo: FakeHabbo) -> None:
    habbo.profiles["Bad"] = {"name": "Bad", "figureString": "<script>"}
    assert api.get("/api/avatars/de/lookup", params={"name": "Bad"}).status_code == 502


def room_document(**changes: object) -> dict:
    return {
        "schema": 1,
        "room": {"width": 8, "height": 8},
        "furni": [
            {"id": 1, "classname": "box", "x": 1, "y": 2, "z": 0, "rot": 2, "state": 0, "future": "kept"}
        ],
        "avatars": [
            {
                "id": 2,
                "name": "A",
                "hotel": "com",
                "figure": FIGURE,
                "x": 3,
                "y": 3,
                "z": 0,
                "dir": 2,
                "pose": "sit",
            }
        ],
        "later": {"wired": True},
        **changes,
    }


def test_room_saves_and_keeps_unknown_fields(api: Api) -> None:
    box_id = api.post("/api/sandboxes", json={"name": "Room"}).json()["id"]
    document = room_document()
    assert (
        api.put(
            f"/api/sandboxes/{box_id}/document", json={"document": document, "base_revision": 1}
        ).status_code
        == 200
    )
    assert api.get(f"/api/sandboxes/{box_id}").json()["document"] == document


@pytest.mark.parametrize(
    "changes",
    [
        {"room": {"width": 0, "height": 8}},
        {"room": {"width": 65, "height": 8}},
        {"room": {"width": 1, "height": 1}},
        {"furni": [{"id": 1, "classname": "../x", "x": 1, "y": 1}]},
        {"furni": [{"id": 1, "classname": "box", "x": -1, "y": 1}]},
        {"furni": [{"id": 1, "classname": "box", "x": "1", "y": 1}]},
        {"furni": "nope"},
        {"avatars": [{"id": 1, "name": "A", "hotel": "evil", "figure": FIGURE, "x": 1, "y": 1}]},
        {"avatars": [{"id": 1, "name": "A", "hotel": "com", "figure": "<script>", "x": 1, "y": 1}]},
        {
            "avatars": [
                {"id": 1, "name": "A", "hotel": "com", "figure": FIGURE, "x": 1, "y": 1, "pose": "fly"}
            ]
        },
    ],
)
def test_bad_rooms_are_refused(api: Api, changes: dict) -> None:
    box_id = api.post("/api/sandboxes", json={"name": "Room"}).json()["id"]
    res = api.put(
        f"/api/sandboxes/{box_id}/document", json={"document": room_document(**changes), "base_revision": 1}
    )
    assert res.status_code == 422
    assert res.json()["error"] == "invalid_room"
    assert "<script>" not in res.text


def test_cached_states_reads_only_what_is_on_disk(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path, None)  # type: ignore[arg-type]
    assert cache.cached_states(7, "switch") is None, "nothing downloaded, and no upstream to ask"
    folder = tmp_path / "7" / "switch"
    folder.mkdir(parents=True)
    (folder / "manifest.v2.json").write_text('{"states": [0, 1, 2]}')
    assert cache.cached_states(7, "switch*3") == [0, 1, 2], "colour variants share one file"
    (folder / "manifest.v2.json").write_text("not json")
    assert cache.cached_states(7, "switch") is None
