"""Room files. Small made-up presets with the shapes seen in real ones, and real ones when available."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from conftest import Api, apply_update
from wiredbench.engine.operations import OPERATION_CODES
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
            {
                "id": 1,
                "classname": "wf_act_change_var_val",
                "x": 1,
                "y": 1,
                "wired": {"from_field": "creation"},
            },
            {"id": 2, "classname": "wf_act_change_var_val", "x": 2, "y": 1, "wired": {"from_field": "value"}},
        ]
    }
    warnings = exchange.export_gpresets(document)[1]
    assert (
        warnings.count("wf_act_change_var_val: the setting from_field cannot go into a G-Presets file yet.")
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
        ("wf_act_toggle_state", "effects", [1], {"toggle_type": "previous"}),
        (
            "wf_cnd_var_age_match",
            "conditions",
            [1, 0, 1, 0, 7777, 2, 0, -10],
            {"compare": "less", "age_of": "update", "duration": 7777, "unit": "minutes"},
        ),
        ("wf_act_give_var", "effects", [1, 0, 7777, 0, 0, -10, 0], {"value": 7777}),
        ("wf_act_give_var", "effects", [1, -1, -5, 0, 0, -10, 0], {"value": -5}),
        ("wf_act_give_var", "effects", [1, 1, 0, 0, 0, -10, 0], {"value": 2**32}),
        (
            "wf_act_change_var_val",
            "effects",
            [1, 3, 0, 0, 77777, -10, 0],
            {"operation": "multiply", "value": 77777},
        ),
        (
            "wf_cnd_var_val_match",
            "conditions",
            [-10, 3, 0, 0, 7777, -10, 0],
            {"compare": "<=", "value": 7777},
        ),
        ("wf_xtra_filter_users_by_var", "addons", [777, 1, 0, 1], {"amount": 777, "lowest": True}),
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


def test_a_millisecond_delay_survives_import_and_export() -> None:
    file = boxed("wf_act_toggle_state", "effects", {"options": [0], "delay": -650})
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    assert document["furni"][0]["wired"]["delay"] == -650
    assert exchange.export_gpresets(document)[0] == file


@pytest.mark.parametrize(
    ("value", "words"), [(-5, [-1, -5]), (7, [0, 7]), (2**32 + 1, [1, 1]), (2**31, [0, -(2**31)])]
)
def test_edited_values_write_both_words(value: int, words: list[int]) -> None:
    file = boxed("wf_act_give_var", "effects", {"options": [1, 0, 3, 0, 0, -10, 0]})
    document, _ = exchange.import_gpresets(file)
    document["furni"][0]["wired"]["value"] = value
    out, _ = exchange.export_gpresets(document)
    assert out["wired"]["effects"][0]["options"] == [1, *words, 0, 0, -10, 0]
    assert exchange.import_gpresets(out)[0]["furni"][0]["wired"]["value"] == value


@pytest.mark.parametrize(("code", "name"), OPERATION_CODES.items())
def test_every_operation_survives_import_and_export(code: int, name: str) -> None:
    options = [1, code, 0, 0, 3, -10, 0]
    file = boxed("wf_act_change_var_val", "effects", {"options": options})
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    assert document["furni"][0]["wired"]["operation"] == name
    assert exchange.export_gpresets(document)[0] == file
    document["furni"][0]["wired"]["operation"] = "set"
    assert exchange.export_gpresets(document)[0]["wired"]["effects"][0]["options"][1] == 0


@pytest.mark.parametrize(
    ("classname", "section", "options", "flag"),
    [
        ("wf_act_give_var", "effects", [1, 0, 3, 0, 1, 1, 1], 4),
        ("wf_act_change_var_val", "effects", [1, 1, 1, 0, 0, 1, 1], 2),
        ("wf_cnd_var_val_match", "conditions", [1, 2, 1, 0, 0, 1, 1], 2),
    ],
)
def test_a_value_source_is_read_and_comes_back_exactly(
    classname: str, section: str, options: list[int], flag: int
) -> None:
    file = boxed(classname, section, {"options": options, "variableIds": ["1", "2"]})
    file["wired"]["variables_map"] = {"a": "1", "b": "2"}
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    assert document["furni"][0]["wired"]["from_variable"] == "b"
    assert exchange.export_gpresets(document)[0] == file

    document["furni"][0]["wired"]["from_variable"] = ""
    out = exchange.export_gpresets(document)[0]["wired"][section][0]
    assert out["options"][flag] == 0
    assert out["variableIds"] == ["1", "0"]


def _with_source(scope_box: str) -> dict[str, Any]:
    return {
        "furni": [
            {"id": 1, "classname": scope_box, "x": 0, "y": 0, "wired": {"variable": "b"}},
            {
                "id": 2,
                "classname": "wf_act_give_var",
                "x": 1,
                "y": 1,
                "wired": {"variable": "a", "from_variable": "b"},
            },
        ]
    }


@pytest.mark.parametrize(
    ("scope_box", "target", "same_holder"),
    [
        ("wf_var_user", 1, 1),
        ("wf_var_furni", 0, 1),
        ("wf_var_room", -10, 0),
        ("wf_var_context", -20, 0),
    ],
)
def test_a_new_value_source_writes_its_target(scope_box: str, target: int, same_holder: int) -> None:
    out, warnings = exchange.export_gpresets(_with_source(scope_box))
    box = out["wired"]["effects"][0]
    assert box["options"][4:7] == [1, target, same_holder]
    assert box["variableIds"][1] == out["wired"]["variables_map"]["b"]
    assert warnings == []


def test_an_undefined_value_source_is_reported() -> None:
    document = _with_source("wf_var_user")
    document["furni"][1]["wired"]["from_variable"] = "nowhere"
    out, warnings = exchange.export_gpresets(document)
    assert out["wired"]["effects"][0]["options"][4] == 0
    assert any("value source" in warning for warning in warnings)


@pytest.mark.parametrize(
    ("scope_box", "target"),
    [("wf_var_user", 1), ("wf_var_furni", 0), ("wf_var_room", -10), ("wf_var_context", -20)],
)
def test_the_target_follows_the_variable(scope_box: str, target: int) -> None:
    document = {
        "furni": [
            {"id": 1, "classname": scope_box, "x": 0, "y": 0, "wired": {"variable": "a"}},
            {"id": 2, "classname": "wf_act_remove_var", "x": 1, "y": 1, "wired": {"variable": "a"}},
        ]
    }
    out, _ = exchange.export_gpresets(document)
    assert out["wired"]["effects"][0]["options"][0] == target


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


def test_furni_listed_with_no_box_settings_stay_that_way() -> None:
    file = {
        "bindings": [],
        "furni": [{"id": 1, "className": "wf_act_log", "rotation": 0, "location": {"x": 1, "y": 1, "z": 0}}],
        "wired": {"effects": [], "triggers": []},
    }
    document, _ = exchange.import_gpresets(json.loads(json.dumps(file)))
    assert exchange.export_gpresets(document)[0] == file
    document["furni"][0]["wired"] = {"text": "edited"}
    out = exchange.export_gpresets(document)[0]
    assert out["wired"]["effects"][0]["config"] == "edited"


def test_selector_options_read_their_positions_and_switches() -> None:
    area = exchange.friendly_settings(
        "wf_slc_users_area", {"options": [3, 4, 5, 6], "filter": True, "inverse": False}, {}
    )
    assert area == {
        "area_x": 3,
        "area_y": 4,
        "area_width": 5,
        "area_height": 6,
        "filter": True,
        "invert": False,
    }
    height = exchange.friendly_settings("wf_slc_furni_altitude", {"options": [150, 2]}, {})
    assert height == {"altitude": 1.5, "altitude_compare": "more"}
    assert exchange.friendly_settings("wf_slc_furni_onfurni", {"options": [3]}, {})["stacking"] == "tile"


def test_selector_settings_export_to_the_box() -> None:
    wired = {"area_x": 3, "area_width": 2, "filter": True, "invert": True}
    document = {
        "room": {"width": 10, "height": 10},
        "furni": [{"id": 1, "classname": "wf_slc_users_area", "x": 1, "y": 1, "wired": wired}],
    }
    out, warnings = exchange.export_gpresets(document)
    box = out["wired"]["selectors"][0]
    assert box["options"] == [3, 0, 2, 0]
    assert (box["filter"], box["inverse"]) == (True, True)
    assert warnings == []


def test_movement_options_read_their_positions() -> None:
    read = exchange.friendly_settings
    assert read("wf_act_rel_mov", {"options": [-3, 4]}, {}) == {"move_x": -3, "move_y": 4}
    assert read("wf_act_set_altitude", {"options": [125, 2]}, {}) == {
        "altitude": 1.25,
        "altitude_change": "set",
    }
    assert read("wf_act_move_rotate_user", {"options": [-1, 9]}, {}) == {
        "user_move": "none",
        "user_turn": "clockwise",
    }
    assert read("wf_act_move_rotate_user", {"options": [2, 4]}, {}) == {"user_move": "x+", "user_turn": "y+"}
    assert read("wf_act_move_rotate", {"options": [8, 1, 1]}, {}) == {
        "direction": "x+y-",
        "rotation": "clockwise",
    }


def test_sources_export_and_read_back() -> None:
    wired = {"text": "hi", "user_source": "selector"}
    furni = [{"id": 1, "classname": "wf_act_show_message", "x": 1, "y": 1, "wired": wired}]
    box = exchange.export_gpresets({"furni": furni})[0]["wired"]["effects"][0]
    assert box["userSources"] == [200]
    assert exchange.friendly_settings("wf_act_show_message", box, {})["user_source"] == "selector"
    fresh = exchange.export_gpresets({"furni": [{**furni[0], "wired": {"text": "hi"}}]})[0]["wired"][
        "effects"
    ][0]
    assert fresh["userSources"] == [0]
    assert "user_source" not in exchange.friendly_settings("wf_act_show_message", fresh, {})


def test_a_new_file_always_has_the_sections_g_presets_needs() -> None:
    furni = [{"id": 1, "classname": "wf_trg_says_something", "x": 1, "y": 1, "wired": {"text": "go"}}]
    wired = exchange.export_gpresets({"furni": furni})[0]["wired"]
    assert wired["conditions"] == []
    assert wired["effects"] == []
    assert len(wired["triggers"]) == 1


def test_team_and_score_options_read_their_positions() -> None:
    read = exchange.friendly_settings
    assert read("wf_act_join_team", {"options": [3, 1]}, {}) == {"team": "blue", "team_type": "banzai"}
    assert read("wf_act_give_score", {"options": [-7, 2]}, {}) == {"points": -7, "times": 2}
    assert read("wf_act_give_score_tm", {"options": [9, 0, 4]}, {})["team"] == "yellow"
    assert read("wf_slc_users_team", {"options": [0]}, {})["team"] == "any"
    assert read("wf_cnd_actor_in_team", {"options": [2]}, {})["team"] == "green"


def test_clock_and_team_score_options_read_their_positions() -> None:
    read = exchange.friendly_settings
    assert read("wf_act_control_clock", {"options": [3]}, {}) == {"clock_control": "pause"}
    assert read("wf_act_adjust_clock", {"options": [12, 3, 1, 2]}, {}) == {
        "clock_seconds": 12,
        "clock_minutes": 3,
        "clock_half": True,
        "clock_change": "set",
    }
    assert read("wf_cnd_counter_time_matches", {"options": [0, 1, 0, 2]}, {})["clock_compare"] == "more"
    assert read("wf_cnd_team_has_score", {"options": [2, 40, 1]}, {}) == {
        "team": "green",
        "points": 40,
        "score_compare": "equal",
    }
