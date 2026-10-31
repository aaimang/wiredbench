"""Keeps Wiredbench's boxes in step with real ones, and room data out of the repository."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from wiredbench.engine import box_facts, coverage
from wiredbench.engine.boxes import BOXES
from wiredbench.services.exchange import (
    OPTION_FIELDS,
    _default,
    _setting_to_option,
    export_gpresets,
    import_gpresets,
)

ROOT = Path(__file__).parents[2]
ALLOWED = {
    "section",
    "type_id",
    "code",
    "numbers",
    "furni_limit",
    "allow_wall_furni",
    "allowed_furni_sources",
    "allowed_user_sources",
    "default_furni_sources",
    "default_user_sources",
    "has_delay",
    "variable_slots",
    "quantifier",
    "filter",
    "invert",
    "context_unread",
}


def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("box_facts_script", ROOT / "scripts/box_facts.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["box_facts_script"] = module
    spec.loader.exec_module(module)
    return module


def test_facts_hold_no_room_data() -> None:
    data = box_facts.load()
    assert set(data) == {"capture", "no_reply", "boxes"}
    assert set(data["capture"]) == {"date", "build", "boxes_unedited"}
    for name, fact in data["boxes"].items():
        assert set(fact) <= ALLOWED, name


def test_deriving_drops_everything_tied_to_a_room() -> None:
    box = {
        "classname": "wf_x", "section": "effect", "type_id": 1, "code": 2, "numbers": [1], "furni_limit": 20,
        "allow_wall_furni": False, "allowed_furni_sources": [], "allowed_user_sources": [],
        "default_furni_sources": [], "default_user_sources": [], "delay": 0, "id": 987654, "x": 11, "y": 12,
        "raw_hex": "deadbeef", "picked_furni_ids": [555], "variable_ids": ["777"], "variables": ["secret"],
        "context": {"secret": 1}, "text": "secret",
    }  # fmt: skip
    dump = {"captured_at": "2026-10-31T20:00:00+0800", "hotel_version": "B1", "room_id": 42, "hotel_host": "secret",
            "variables": [{"name": "secret"}], "boxes": [box, {"classname": "wf_y", "not_read": True}]}  # fmt: skip
    text = json.dumps(script().derive(dump))
    for leaked in ("secret", "987654", "deadbeef", "555", "777", '"room_id"'):
        assert leaked not in text
    facts = json.loads(text)
    assert facts["no_reply"] == ["wf_y"]
    assert facts["boxes"]["wf_x"]["has_delay"] is True
    assert facts["boxes"]["wf_x"]["variable_slots"] == 1


def test_tracker_records_every_box_in_the_dump() -> None:
    tracker = coverage.load()
    data = box_facts.load()
    assert tracker["dump_capture"] == {"date": data["capture"]["date"], "build": data["capture"]["build"]}
    seen = {name for name, entry in tracker["boxes"].items() if entry.get("dump")}
    assert seen == set(data["boxes"])
    for name in data["no_reply"]:
        assert "dump" not in tracker["boxes"][name]
        assert tracker["boxes"][name]["note"]


def test_sections_match_real_boxes() -> None:
    for name, spec in BOXES.items():
        fact = box_facts.of(name)
        assert fact is None or fact["section"] == spec["kind"], name


def test_defaults_match_real_boxes() -> None:
    for name, fields in OPTION_FIELDS.items():
        fact = box_facts.of(name)
        assert fact, name
        for field, position, reader in fields:
            assert position < len(fact["numbers"]), (name, field)
            assert _setting_to_option(_default(name, field), reader) == fact["numbers"][position], (
                name,
                field,
            )


def test_every_default_number_can_be_read() -> None:
    for name, fields in OPTION_FIELDS.items():
        fact = box_facts.of(name)
        assert fact
        document, _ = import_gpresets(_preset(name, fact))
        settings = document["furni"][0]["wired"]
        for field, _, _ in fields:
            assert settings[field] == _default(name, field), (name, field)


def _preset(name: str, fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "furni": [{"id": 1, "className": name, "location": {"x": 1, "y": 1}}],
        "wired": {f"{fact['section']}s": [{"wiredId": 1, "options": fact["numbers"]}]},
    }


def test_new_boxes_start_from_real_defaults() -> None:
    out, warnings = export_gpresets(
        {
            "furni": [
                {"id": 1, "classname": "wf_act_give_var", "x": 1, "y": 1},
                {"id": 2, "classname": "wf_cnd_trggrer_on_frn", "x": 2, "y": 1},
                {"id": 3, "classname": "wf_slc_users_with_var", "x": 3, "y": 1},
                {"id": 4, "classname": "wf_act_move_rotate", "x": 4, "y": 1, "wired": {"rotation": "random"}},
                {"id": 5, "classname": "wf_xtra_never_seen", "x": 5, "y": 1},
            ]
        }
    )
    give, move = out["wired"]["effects"]
    assert give["options"] == [1, 0, 0, 0, 0, -10, 0]
    assert (give["furniSources"], give["userSources"], give["variableIds"]) == (
        [0, 200],
        [0, 200],
        ["0", "0"],
    )
    assert give["delay"] == 0
    assert out["wired"]["conditions"][0]["quantifier"] == 0
    assert "filter" in out["wired"]["selectors"][0]
    assert move["options"] == [0, 3, 1], "the unnamed third number keeps its real default"
    assert [w for w in warnings if "never_seen" in w] and len(warnings) == 1


def test_availability_numbers_differ_by_variable_type() -> None:
    def availability(name: str, options: list[int]) -> Any:
        document, _ = import_gpresets(_preset(name, {"section": "variable", "numbers": options}))
        return document["furni"][0]["wired"]["availability"]

    assert availability("wf_var_user", [0, 0]) == "active"
    assert availability("wf_var_user", [10, 0]) == "persistent"
    assert availability("wf_var_furni", [0, 1]) == "active"
    assert availability("wf_var_furni", [0, 10]) == "persistent"
    assert availability("wf_var_room", [1]) == "active"
    assert availability("wf_var_room", [11]) == "shared"
