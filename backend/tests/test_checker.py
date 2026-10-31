"""The stack checker: what it reports, and just as much what it must not report."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import Api
from test_exchange import preset
from wiredbench.engine.checker import check_room
from wiredbench.engine.tutorials import TUTORIALS
from wiredbench.services import exchange


def box(furni_id: int, classname: str, x: int, y: int, z: float = 0, **settings: Any) -> dict[str, Any]:
    return {"id": furni_id, "classname": classname, "x": x, "y": y, "z": z, "wired": settings}


def plain(furni_id: int, classname: str, x: int, y: int) -> dict[str, Any]:
    return {"id": furni_id, "classname": classname, "x": x, "y": y, "z": 0}


def codes(*furni: dict[str, Any]) -> list[str]:
    return [issue["code"] for issue in check_room({"furni": list(furni)})]


@pytest.mark.parametrize("slug", list(TUTORIALS))
def test_example_rooms_have_no_errors_or_warnings(slug: str) -> None:
    issues = check_room(TUTORIALS[slug]["build"]("sandbox"))
    assert [i for i in issues if i["severity"] != "info"] == []


def test_a_working_stack_is_clean() -> None:
    assert (
        codes(
            plain(1, "wf_floor_switch1", 1, 1),
            box(2, "wf_trg_state_changed", 2, 2, furni=[1]),
            box(3, "wf_act_toggle_state", 2, 2, 0.65, furni=[1]),
        )
        == []
    )


def test_empty_room_and_lone_utility_boxes_are_fine() -> None:
    assert check_room({}) == []
    assert codes(plain(1, "wf_antenna1", 1, 1), plain(2, "chair", 2, 2)) == []


def test_effects_with_no_trigger() -> None:
    assert "no_trigger" in codes(box(1, "wf_act_log", 1, 1, text="x"))


def test_a_called_stack_needs_no_trigger() -> None:
    found = codes(
        box(1, "wf_trg_enter_room", 1, 1),
        box(2, "wf_act_call_stacks", 1, 1, 0.65, furni=[3]),
        box(3, "wf_act_log", 2, 2, text="x"),
    )
    assert "no_trigger" not in found


def test_trigger_with_no_effect() -> None:
    assert "no_effect" in codes(box(1, "wf_trg_enter_room", 1, 1))


def test_variable_only_stacks_are_fine() -> None:
    assert (
        codes(
            box(1, "wf_var_user", 1, 1, variable="score"),
            box(2, "wf_xtra_var_time_util", 1, 1, 0.65, variable="score"),
        )
        == []
    )


def test_missing_settings() -> None:
    found = codes(
        box(1, "wf_trg_click_furni", 1, 1),
        box(2, "wf_act_log", 1, 1, 0.65, text="x"),
        box(3, "wf_trg_recv_signal", 2, 2),
        box(4, "wf_act_log", 2, 2, 0.65, text="x"),
        box(5, "wf_trg_says_something", 3, 3),
        box(6, "wf_act_remove_var", 3, 3, 0.65),
    )
    for code in ("no_picks", "no_antenna", "no_keyword", "no_variable"):
        assert code in found


def test_match_all_needs_no_keyword() -> None:
    found = codes(
        box(1, "wf_trg_says_something", 1, 1, match="all"), box(2, "wf_act_log", 1, 1, 0.65, text="x")
    )
    assert "no_keyword" not in found


def test_picks_of_furni_that_are_gone() -> None:
    assert "missing_furni" in codes(
        box(1, "wf_trg_click_furni", 1, 1, furni=[99]), box(2, "wf_act_log", 1, 1, 0.65)
    )


def test_signals_need_both_ends() -> None:
    antenna = plain(1, "wf_antenna1", 0, 0)
    sender = [box(2, "wf_trg_enter_room", 1, 1), box(3, "wf_act_send_signal", 1, 1, 0.65, antenna=[1])]
    receiver = [box(4, "wf_trg_recv_signal", 2, 2, antenna=[1]), box(5, "wf_act_log", 2, 2, 0.65, text="x")]
    assert "no_receiver" in codes(antenna, *sender)
    assert "no_sender" in codes(antenna, *receiver)
    both = codes(antenna, *sender, *receiver)
    assert "no_receiver" not in both
    assert "no_sender" not in both


def test_sources_need_what_they_read() -> None:
    found = codes(
        box(1, "wf_trg_enter_room", 1, 1),
        box(2, "wf_act_show_message", 1, 1, 0.65, text="x", user_source="selector"),
        box(3, "wf_act_show_message", 1, 1, 1.3, text="x", user_source="signal"),
    )
    assert "no_selector" in found
    assert "no_signal" in found


def test_variables_must_be_defined_once() -> None:
    found = codes(box(1, "wf_trg_enter_room", 1, 1), box(2, "wf_act_give_var", 1, 1, 0.65, variable="ghost"))
    assert "undefined_variable" in found
    assert "variable_clash" in codes(
        box(1, "wf_var_user", 1, 1, variable="a"), box(2, "wf_var_room", 2, 2, variable="a")
    )
    internal = codes(
        box(1, "wf_trg_enter_room", 1, 1),
        box(2, "wf_act_change_var_val", 1, 1, 0.65, variable="x", from_variable="@level"),
        box(3, "wf_var_user", 2, 2, variable="x"),
    )
    assert "undefined_variable" not in internal


def test_unsimulated_boxes_are_reported_once_as_information() -> None:
    issues = check_room(
        {
            "furni": [
                box(1, "wf_act_new_thing", 1, 1),
                box(2, "wf_act_new_thing", 2, 2),
                box(3, "wf_trg_enter_room", 1, 1),
            ]
        }
    )
    notes = [i for i in issues if i["code"] == "not_simulated"]
    assert len(notes) == 1
    assert notes[0]["severity"] == "info"


def test_imported_boxes_are_not_blamed_for_settings_not_read_yet() -> None:
    document, _ = exchange.import_gpresets(preset())
    found = [i["code"] for i in check_room(document)]
    assert "no_picks" not in found
    assert "no_variable" not in found
    assert "undefined_variable" not in found


def test_results_are_ordered_and_located() -> None:
    issues = check_room(
        {
            "furni": [
                box(1, "wf_act_new_thing", 1, 1),
                box(2, "wf_trg_click_furni", 5, 6),
                box(3, "wf_act_log", 5, 6, 0.65),
            ]
        }
    )
    assert issues[0]["severity"] == "error"
    assert (issues[0]["x"], issues[0]["y"], issues[0]["box"]) == (5, 6, 2)


def test_check_over_the_api(api: Api) -> None:
    room = api.post("/api/tutorials/switch-flip", json={}).json()["id"]
    assert [
        i for i in api.get(f"/api/sandboxes/{room}/check").json()["issues"] if i["severity"] != "info"
    ] == []
    assert api.get("/api/sandboxes/999/check").status_code == 404
