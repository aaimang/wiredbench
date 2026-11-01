"""Keeps the tracker honest: nothing may go missing, and evidence must be well formed."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from conftest import Api, FakeHabbo, apply_update, furni, furnidata
from wiredbench.engine import coverage
from wiredbench.engine.boxes import BOXES
from wiredbench.services import exchange, room
from wiredbench.services.exchange import OPTION_FIELDS

SCRIPTS = Path(__file__).parents[2] / "scripts"


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_every_box_wiredbench_knows_is_tracked() -> None:
    tracked = set(coverage.load()["boxes"])
    assert len(tracked) >= 284
    assert set(BOXES) - tracked == set()
    assert set(OPTION_FIELDS) - tracked == set()


def test_room_checks_have_dates_and_nothing_else_is_claimed() -> None:
    for name, entry in coverage.load()["boxes"].items():
        assert set(entry) <= {"reference", "preset", "dump", "room", "note"}, name
        if "room" in entry:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["room"]), name
    assert coverage.room_checked() == {
        "wf_act_change_var_val",
        "wf_act_furni_to_user",
        "wf_act_move_rotate",
        "wf_act_move_rotate_user",
        "wf_act_rel_mov",
        "wf_act_set_altitude",
        "wf_act_show_message",
        "wf_act_toggle_state",
        "wf_cnd_var_age_match",
        "wf_cnd_var_val_match",
        "wf_floor_switch1",
        "wf_slc_furni_altitude",
        "wf_slc_furni_area",
        "wf_slc_furni_onfurni",
        "wf_slc_furni_picks",
        "wf_slc_users_area",
        "wf_trg_says_something",
        "wf_trg_state_changed",
        "wf_var_room",
    }


def test_evidence_order() -> None:
    assert coverage.level({}) == "unknown"
    assert coverage.level({"reference": True}) == "from_reference"
    assert coverage.level({"reference": True, "preset": True}) == "real_preset"
    assert coverage.level({"preset": True, "dump": True}) == "real_dump"
    assert coverage.level({"dump": True, "room": "2026-10-31"}) == "real_room"


def test_summary_adds_up() -> None:
    total = coverage.summary()
    assert sum(total[name] for name in coverage.LEVELS) == total["total"]
    assert total["options_mapped"] == len(OPTION_FIELDS)
    assert total["has_form"] == len(BOXES)


def test_guide_shows_evidence_and_flags_new_boxes(api: Api, habbo: FakeHabbo) -> None:
    habbo.set(furnidata(furni("wf_act_toggle_state"), furni("wf_act_never_seen_before")), 'W/"new"')
    apply_update(api)
    body = api.get("/api/guide", params={"hotel": "sandbox"}).json()
    rows = {row["classname"]: row for row in body["rows"]}
    assert rows["wf_act_toggle_state"]["evidence"] == "real_room"
    assert rows["wf_act_toggle_state"]["room_checked_on"] == "2026-10-31"
    assert rows["wf_act_never_seen_before"]["evidence"] == "new"
    assert body["coverage"]["total"] >= 284


def test_updating_evidence_only_adds(tmp_path: Path, monkeypatch: Any) -> None:
    module = script("box_coverage")
    tracker = tmp_path / "t.json"
    tracker.write_text(json.dumps({"boxes": {"wf_a": {"room": "2026-01-01"}}}))
    monkeypatch.setattr(module, "TRACKER", tracker)
    data = tmp_path / "f.json"
    items = [{"classname": "wf_b*2"}, {"classname": "chair"}]
    data.write_text(json.dumps({"roomitemtypes": {"furnitype": items}, "wallitemtypes": {"furnitype": []}}))
    monkeypatch.setattr(sys, "argv", ["x", "--furnidata", str(data)])
    module.main()
    assert json.loads(tracker.read_text())["boxes"] == {"wf_a": {"room": "2026-01-01"}, "wf_b": {}}


def test_proof_preset_uses_unusual_values_that_read_back() -> None:
    module = script("proof_preset")
    preset, expected = module.build("all")
    assert set(expected) == set(OPTION_FIELDS)
    document, report = exchange.import_gpresets(json.loads(json.dumps(preset)))
    room.validate(document)
    assert report["not_placed"] == 0
    for item in document["furni"]:
        settings = expected[item["classname"]]["settings"]
        defaults = {f["name"]: f["default"] for f in BOXES[item["classname"]]["fields"]}
        for name, _, _ in OPTION_FIELDS[item["classname"]]:
            assert item["wired"][name] == settings[name], (item["classname"], name)
            assert settings[name] != defaults[name], (item["classname"], name)
    assert "wf_trg_says_something" in module.checklist("all", expected)
    assert module.build("triggers")[1].keys() < expected.keys()
