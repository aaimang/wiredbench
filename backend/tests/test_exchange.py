"""Room files. Small made-up presets with the shapes seen in real ones, and real ones when available."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from conftest import Api, apply_update
from wiredbench.services import exchange, room

SAMPLES = os.environ.get("WB_PRESET_SAMPLES")


def preset() -> dict[str, Any]:
    return {
        "bindings": [],
        "floorplan": "000\r000\r000",
        "recolorables": {"kept": True},
        "somethingNew": [1, 2],
        "furni": [
            {
                "rotation": 4,
                "name": "fridge[0]",
                "className": "ktchn_fridge",
                "id": 1,
                "state": "0",
                "location": {"x": 0, "y": 2, "z": 0},
            },
            {
                "rotation": 6,
                "name": "wf[0]",
                "className": "wf_trg_state_changed",
                "id": 2,
                "location": {"x": 1, "y": 0, "z": 0.5},
            },
            {
                "rotation": 0,
                "name": "act[0]",
                "className": "wf_act_toggle_state",
                "id": 3,
                "state": "weird",
                "variables": {"100": 0},
                "location": {"x": 1, "y": 0, "z": 1.15},
            },
            {
                "rotation": 0,
                "name": "var[0]",
                "className": "wf_var_room",
                "id": 4,
                "location": {"x": 2, "y": 0, "z": 0},
            },
            {
                "rotation": 0,
                "name": "odd[0]",
                "className": "wf_xtra_new_thing",
                "id": 5,
                "location": {"x": 2, "y": 1, "z": 0},
            },
            {
                "rotation": 0,
                "name": "give[0]",
                "className": "wf_act_give_var",
                "id": 6,
                "location": {"x": 2, "y": 2, "z": 0},
            },
        ],
        "wired": {
            "triggers": [
                {
                    "secondItems": [],
                    "furniSources": [100],
                    "wiredId": 2,
                    "userSources": [],
                    "variableIds": [],
                    "options": [],
                    "config": "",
                    "items": [1],
                }
            ],
            "effects": [
                {
                    "secondItems": [],
                    "furniSources": [200],
                    "wiredId": 3,
                    "userSources": [],
                    "delay": 5,
                    "variableIds": [],
                    "options": [0],
                    "config": "",
                    "items": [],
                },
                {
                    "secondItems": [],
                    "furniSources": [100],
                    "wiredId": 6,
                    "userSources": [200],
                    "delay": 0,
                    "variableIds": ["700"],
                    "options": [1, 0, 0, 0],
                    "config": "",
                    "items": [],
                },
            ],
            "variables": [
                {
                    "secondItems": [],
                    "furniSources": [],
                    "wiredId": 4,
                    "userSources": [],
                    "variableIds": [],
                    "options": [1],
                    "config": "clock",
                    "items": [],
                    "variableId": "700",
                }
            ],
            "addons": [
                {"wiredId": 5, "options": [9, 9], "config": "mystery", "futureField": {"a": 1}},
                {"wiredId": 999, "options": [1], "config": "box with no furni"},
            ],
            "conditions": [],
            "selectors": [],
            "variables_map": {"clock": "700", "other": "701"},
        },
    }


def round_trip(file: dict[str, Any]) -> dict[str, Any]:
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    room.validate(document)
    out, _ = exchange.export_gpresets(document)
    return out


def test_an_untouched_file_comes_back_exactly() -> None:
    assert round_trip(preset()) == preset()


def test_import_reads_what_it_can() -> None:
    document, report = exchange.import_gpresets(preset())
    by_id = {item["id"]: item for item in document["furni"]}
    assert (by_id[1]["x"], by_id[1]["y"], by_id[1]["rot"]) == (0, 2, 4)
    assert by_id[2]["wired"]["furni"] == [1]
    assert by_id[3]["wired"]["delay"] == 5
    assert by_id[3]["state"] == 0, "a text state reads as 0 and is kept in the original data"
    assert by_id[4]["wired"]["variable"] == "clock"
    assert by_id[6]["wired"]["variable"] == "clock", "IDs become names through the map"
    assert document["room"] == {"width": 12, "height": 12}
    assert report["not_simulated"] == {"wf_xtra_new_thing": 1}
    assert report["not_placed"] == 1


def test_edits_change_only_what_was_edited() -> None:
    document, _ = exchange.import_gpresets(preset())
    by_id = {item["id"]: item for item in document["furni"]}
    by_id[1]["x"] = 5
    by_id[1]["state"] = 3
    by_id[3]["wired"]["delay"] = 9
    by_id[2]["wired"]["furni"] = [1, 3]
    by_id[6]["wired"]["variable"] = "other"
    out, _ = exchange.export_gpresets(document)
    want = preset()
    want["furni"][0]["location"]["x"] = 5
    want["furni"][0]["state"] = "3"
    want["wired"]["effects"][0]["delay"] = 9
    want["wired"]["triggers"][0]["items"] = [1, 3]
    want["wired"]["effects"][1]["variableIds"] = ["701"]
    assert out == want


def test_removed_furni_take_their_boxes_with_them() -> None:
    document, _ = exchange.import_gpresets(preset())
    document["furni"] = [item for item in document["furni"] if item["id"] != 3]
    out, _ = exchange.export_gpresets(document)
    assert [box["wiredId"] for box in out["wired"]["effects"]] == [6]


def test_a_partial_file_is_kept() -> None:
    partial = {"wired": {"addons": [{"wiredId": 8, "config": "x"}], "variables_map": {}}}
    document, report = exchange.import_gpresets(json.loads(json.dumps(partial)))
    assert document["furni"] == []
    assert report["partial"] is True
    assert exchange.export_gpresets(document)[0] == partial


def test_new_rooms_export_with_known_values_and_warnings() -> None:
    document = {
        "furni": [
            {"id": 1, "classname": "wf_floor_switch1", "x": 1, "y": 1},
            {"id": 2, "classname": "wf_trg_state_changed", "x": 2, "y": 2, "wired": {"furni": [1]}},
            {
                "id": 3,
                "classname": "wf_act_toggle_state",
                "x": 2,
                "y": 2,
                "z": 0.65,
                "wired": {"furni": [1], "delay": 2},
            },
            {"id": 4, "classname": "wf_var_room", "x": 3, "y": 3, "wired": {"variable": "score"}},
            {"id": 5, "classname": "wf_xtra_unknown", "x": 3, "y": 4},
        ],
        "avatars": [{"id": 9}],
    }
    out, warnings = exchange.export_gpresets(document)
    assert out["furni"][0]["className"] == "wf_floor_switch1"
    assert out["wired"]["triggers"][0]["furniSources"] == [100]
    assert out["wired"]["triggers"][0]["items"] == [1]
    assert out["wired"]["effects"][0]["options"] == [0]
    assert out["wired"]["effects"][0]["furniSources"] == [100], "it has picks"
    assert out["wired"]["effects"][0]["delay"] == 2
    variable = out["wired"]["variables"][0]
    assert variable["config"] == "score"
    assert out["wired"]["variables_map"] == {"score": variable["variableId"]}
    assert any("wf_xtra_unknown" in w for w in warnings)
    assert any("Avatars" in w for w in warnings)
    assert not any("wf_trg_state_changed" in w for w in warnings)


@pytest.mark.parametrize(
    "file",
    [
        {"furni": "nope"},
        {"furni": [{"id": 1}]},
        {"furni": [{"className": "a", "id": 0, "location": {"x": 1, "y": 1}}]},
        {"furni": [{"className": "a", "id": 1}]},
        {"furni": [{"className": "a", "id": 1, "location": {"x": 900, "y": 1}}]},
        {"furni": [{"className": "a", "id": 1, "location": {"x": 1.5, "y": 1}}]},
        {"furni": [{"className": "a", "id": 1, "location": {"x": True, "y": 1}}]},
        {
            "furni": [
                {"className": "a", "id": 1, "location": {"x": 1, "y": 1}},
                {"className": "b", "id": 1, "location": {"x": 1, "y": 1}},
            ]
        },
        {"furni": [], "floorplan": "\r".join(["0" * 200])},
    ],
)
def test_bad_files_are_refused(api: Api, file: dict[str, Any]) -> None:
    res = api.post("/api/import", json={"file": file})
    assert res.status_code == 422, res.text


def test_not_a_room_file(api: Api) -> None:
    res = api.post("/api/import", json={"file": {"hello": "world"}})
    assert res.status_code == 422
    assert res.json()["error"] == "invalid_room_file"
    assert (
        api.post(
            "/api/import", json={"file": {"format": "wiredbench", "version": 99, "document": {}}}
        ).status_code
        == 422
    )


def test_import_and_export_over_the_api(api: Api) -> None:
    apply_update(api)
    res = api.post("/api/import", json={"file": preset(), "name": "From file"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "From file"
    assert body["report"]["furni"] == 6
    assert any("catalogue" in w for w in body["report"]["warnings"])
    room_id = body["id"]
    assert (
        api.post("/api/import", json={"file": preset(), "name": "From file"}).json()["name"]
        == "From file (copy)"
    )

    out = api.get(f"/api/sandboxes/{room_id}/export", params={"format": "gpresets"}).json()
    assert out["file"] == preset()
    assert out["filename"] == "From-file.json"
    rows = {row["classname"]: row for row in out["report"]["shopping_list"]}
    assert rows["ktchn_fridge"]["count"] == 1
    assert rows["ktchn_fridge"]["stage"] == "unknown"
    assert any("ktchn_fridge" in w for w in out["report"]["warnings"])


def test_native_round_trip_keeps_everything(api: Api) -> None:
    first = api.post("/api/import", json={"file": preset(), "name": "Original"}).json()["id"]
    native = api.get(f"/api/sandboxes/{first}/export").json()
    assert native["filename"] == "Original.wiredbench.json"
    assert native["file"]["format"] == "wiredbench"
    second = api.post("/api/import", json={"file": native["file"]}).json()
    assert second["name"] == "Original (copy)"
    assert (
        api.get(f"/api/sandboxes/{second['id']}").json()["document"]
        == api.get(f"/api/sandboxes/{first}").json()["document"]
    )
    assert (
        api.get(f"/api/sandboxes/{second['id']}/export", params={"format": "gpresets"}).json()["file"]
        == preset()
    )


def test_exports_never_contain_api_keys(api: Api) -> None:
    room_id = api.post("/api/tutorials/time-tracking", json={}).json()["id"]
    keys = api.post(f"/api/sandboxes/{room_id}/api-keys", json={}).json()
    for format_name in ("native", "gpresets"):
        text = api.get(f"/api/sandboxes/{room_id}/export", params={"format": format_name}).text
        assert keys["read_key"] not in text
        assert keys["write_key"] not in text


def test_an_imported_room_runs(api: Api) -> None:
    room_id = api.post("/api/import", json={"file": preset()}).json()["id"]
    assert api.post(f"/api/sandboxes/{room_id}/run", json={"seed": 1}).status_code == 201
    state = api.post(
        f"/api/sandboxes/{room_id}/run/input", json={"type": "use", "user": 1, "furni": 1}
    ).json()
    assert next(item["state"] for item in state["furni"] if item["id"] == 1) == 1


@pytest.mark.skipif(not SAMPLES, reason="Set WB_PRESET_SAMPLES to a folder of real preset files.")
def test_real_files_come_back_exactly() -> None:
    files = sorted(Path(SAMPLES or "").glob("*.json"))
    assert files
    for path in files:
        original = json.loads(path.read_text(encoding="utf-8"))
        assert round_trip(original) == original, path.name


def test_settings_that_cannot_be_written_are_reported() -> None:
    document = {
        "furni": [
            {"id": 1, "classname": "wf_act_change_var_val", "x": 1, "y": 1, "wired": {"operation": "add"}},
            {"id": 2, "classname": "wf_act_change_var_val", "x": 2, "y": 1, "wired": {"operation": "set"}},
        ]
    }
    warnings = exchange.export_gpresets(document)[1]
    assert (
        warnings.count("wf_act_change_var_val: the setting operation cannot go into a G-Presets file yet.")
        == 1
    )


def boxed(classname: str, section: str, box: dict[str, Any]) -> dict[str, Any]:
    return {
        "bindings": [],
        "furni": [
            {
                "id": 1,
                "className": classname,
                "name": "a",
                "rotation": 0,
                "location": {"x": 1, "y": 1, "z": 0},
            }
        ],
        "wired": {section: [{"wiredId": 1, "config": "", **box}]},
    }


@pytest.mark.parametrize(
    ("classname", "section", "options", "expected"),
    [
        (
            "wf_trg_says_something",
            "triggers",
            [0, 1, 1],
            {"owner_only": False, "match": "exact", "hide_message": True},
        ),
        ("wf_trg_periodically", "triggers", [5], {"seconds": 2.5}),
        ("wf_trg_period_long", "triggers", [12], {"seconds": 60}),
        ("wf_xtra_execution_limit", "addons", [10, 3], {"count": 10, "window_seconds": 1.5}),
        ("wf_xtra_filter_users", "addons", [1, 0, 1], {"amount": 1}),
        ("wf_cnd_user_count_in", "conditions", [2, 8], {"min": 2, "max": 8}),
        ("wf_act_user_to_furni", "effects", [2], {"walking": "stop"}),
        ("wf_act_move_rotate", "effects", [0, 3], {"rotation": "random"}),
        (
            "wf_xtra_text_output_variable",
            "addons",
            [0, -20, 1],
            {"placeholder_type": "single", "display": "textual"},
        ),
        ("wf_var_user", "variables", [10, 1], {"availability": "persistent", "has_value": True}),
        ("wf_var_furni", "variables", [1, 10], {"availability": "persistent", "has_value": True}),
        ("wf_var_context", "variables", [1], {"has_value": True}),
    ],
)
def test_option_numbers_read_as_settings(
    classname: str, section: str, options: list[int], expected: dict[str, Any]
) -> None:
    file = boxed(classname, section, {"options": options})
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    settings = document["furni"][0]["wired"]
    assert {key: settings[key] for key in expected} == expected
    assert exchange.export_gpresets(document)[0] == file, "untouched settings must not change the numbers"


def test_edited_settings_write_their_numbers() -> None:
    file = boxed("wf_trg_says_something", "triggers", {"options": [0, 1, 1]})
    document, _ = exchange.import_gpresets(file)
    document["furni"][0]["wired"].update(match="all", owner_only=True, hide_message=False)
    out, warnings = exchange.export_gpresets(document)
    assert out["wired"]["triggers"][0]["options"] == [1, 2, 0]
    assert warnings == []


def test_new_boxes_write_options_from_their_settings() -> None:
    document = {
        "furni": [
            {
                "id": 1,
                "classname": "wf_trg_says_something",
                "x": 1,
                "y": 1,
                "wired": {"text": "hi", "match": "exact"},
            },
            {"id": 2, "classname": "wf_trg_periodically", "x": 2, "y": 1, "wired": {"seconds": 10}},
            {"id": 3, "classname": "wf_trg_says_something", "x": 3, "y": 1},
        ]
    }
    out, warnings = exchange.export_gpresets(document)
    triggers = out["wired"]["triggers"]
    assert triggers[0]["options"] == [0, 1, 1]
    assert triggers[1]["options"] == [20]
    assert triggers[2]["options"] == [0, 0, 1]
    assert warnings == []


def test_unreadable_option_numbers_are_left_alone() -> None:
    file = boxed("wf_trg_says_something", "triggers", {"options": [0, 9, "x"]})
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    assert "match" not in document["furni"][0]["wired"]
    assert exchange.export_gpresets(document)[0] == file
