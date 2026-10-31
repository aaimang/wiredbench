from __future__ import annotations

import json

import pytest

from conftest import furni, furnidata
from wiredbench.services.furnidata import (
    InvalidFurnidata,
    classify_wired,
    diff,
    parse,
    release_stage,
    summarise,
)


@pytest.mark.parametrize(
    "classname,expected",
    [
        ("wf_trg_says_something", (True, "trigger")),
        ("wf_act_move_rotate", (True, "effect")),
        ("wf_cnd_trggrer_on_frn", (True, "condition")),
        ("wf_slc_furni_by_type", (True, "selector")),
        ("wf_xtra_random", (True, "addon")),
        ("wf_var_user", (True, "variable")),
        ("wf_test_act", (True, "effect")),
        ("wf_ltdproto_act_toggle_state", (True, "effect")),
        ("wf_proto_cnd_trggrer_on_frn", (True, "condition")),
        ("wf_antenna1", (True, "utility")),
        ("conf_wired_disable", (True, "utility")),
        ("chair_act", (False, None)),
        ("post.it", (False, None)),
    ],
)
def test_classify_wired(classname: str, expected: tuple[bool, str | None]) -> None:
    assert classify_wired(classname) == expected


def test_release_stage_signals() -> None:
    assert release_stage("wf_act_x", {"offerid": 5, "bc": False}) == "live"
    assert release_stage("wf_act_x", {"offerid": -1, "bc": True}) == "live"
    assert release_stage("wf_act_x", {"offerid": -1, "bc": False}) == "not_in_catalogue"
    assert release_stage("wf_act_x", {"offerid": 0, "bc": False}) == "not_in_catalogue"
    assert (
        release_stage("wf_act_x", {"offerid": 5, "bc": True, "name": "wf_act_x name"}) == "not_in_catalogue"
    )
    assert release_stage("chair", {"offerid": -1, "bc": False}) == "live"


def test_parse_floor_and_wall() -> None:
    raw = furnidata(furni("chair"), furni("wf_act_x"), wall=(furni("post.it"),))
    parsed = parse(json.dumps(raw).encode())
    assert {item["classname"]: item["kind"] for item in parsed.items} == {
        "chair": "floor",
        "wf_act_x": "floor",
        "post.it": "wall",
    }
    assert parsed.wired_count == 1


def test_real_shape_of_classnames_is_kept() -> None:
    raw = furnidata(furni("chair_plasto*1"), furni("post.it"), furni("a-b"))
    assert parse(json.dumps(raw).encode()).skipped == 0


@pytest.mark.parametrize(
    "bad", ["", "../../etc/passwd", "a/b", "a\\b", ".hidden", "a..b", "<img>", "a b", "x" * 161, "a\nb"]
)
def test_unsafe_classnames_are_skipped(bad: str) -> None:
    raw = furnidata(furni("chair"), furni(bad))
    parsed = parse(json.dumps(raw).encode())
    assert [item["classname"] for item in parsed.items] == ["chair"]
    assert parsed.skipped == 1


def test_duplicates_and_bad_entries_are_skipped() -> None:
    raw = furnidata(furni("chair"), furni("chair"), {"classname": "no_id"}, furni("x", id="12"))
    parsed = parse(json.dumps(raw).encode())
    assert len(parsed.items) == 1
    assert parsed.skipped == 3


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"roomitemtypes": {"furnitype": []}}',
        b'{"roomitemtypes": {"furnitype": []}, "wallitemtypes": {"furnitype": []}}',
        b'{"roomitemtypes": {"furnitype": "x"}, "wallitemtypes": {"furnitype": []}}',
    ],
)
def test_invalid_files_are_refused(raw: bytes) -> None:
    with pytest.raises(InvalidFurnidata):
        parse(raw)


def test_diff_finds_new_changed_removed_with_wired_first() -> None:
    old = {
        "chair": {"name": "Chair", "revision": 1},
        "lamp": {"name": "Lamp"},
        "wf_act_old": {"name": "Old"},
        "wf_act_same": {"name": "Same"},
        "sofa": {"name": "Sofa"},
    }
    new = {
        "chair": {"name": "Chair", "revision": 2},
        "wf_act_same": {"name": "Same"},
        "wf_trg_new": {"name": "New"},
        "table": {"name": "Table"},
        "sofa": {"name": "Sofa", "bc": True},
    }
    entries = diff(old, new)
    assert [(e["classname"], e["change"]) for e in entries] == [
        ("wf_trg_new", "new"),
        ("wf_act_old", "removed"),
        ("table", "new"),
        ("chair", "changed"),
        ("sofa", "changed"),
        ("lamp", "removed"),
    ]
    chair = next(e for e in entries if e["classname"] == "chair")
    assert chair["fields"] == [{"field": "revision", "old": 1, "new": 2}]
    sofa = next(e for e in entries if e["classname"] == "sofa")
    assert sofa["fields"] == [{"field": "bc", "old": None, "new": True}]
    assert summarise(entries) == {
        "wired_new": 1,
        "wired_changed": 0,
        "wired_removed": 1,
        "other_new": 1,
        "other_changed": 2,
        "other_removed": 1,
    }


def test_identical_versions_have_no_differences() -> None:
    same = {"chair": {"name": "Chair"}}
    assert diff(same, dict(same)) == []
