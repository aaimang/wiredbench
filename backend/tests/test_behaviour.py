"""scripts/behaviour.py: two engines' checkpoints compared, category by category."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "behaviour.py"
_SPEC = importlib.util.spec_from_file_location("behaviour", _PATH)
assert _SPEC and _SPEC.loader
behaviour = importlib.util.module_from_spec(_SPEC)
sys.modules["behaviour"] = behaviour
_SPEC.loader.exec_module(behaviour)

POINT = {
    "at": 0,
    "users": {"1": [0, 0]},
    "furni": {"5": [1, 1, 0, 0]},
    "variables": {"v": {"user:1": "3"}},
    "messages": [],
}


def scenario(*points: dict) -> dict:
    return {"inputs": [{"type": "say", "user": 1, "text": "go", "at_ms": 0}], "python": list(points)}


def test_the_same_checkpoints_match() -> None:
    assert behaviour._compare(scenario(POINT, POINT), {"checkpoints": [POINT, POINT]})["status"] == "same"


def test_a_difference_is_reported_at_its_first_checkpoint_by_category() -> None:
    theirs = POINT | {"variables": {"v": {"user:1": "4"}}, "messages": ["hi"]}
    result = behaviour._compare(scenario(POINT, POINT), {"checkpoints": [POINT, theirs]})

    assert result["status"] == "differs"
    assert result["categories"] == ["messages", "variables"]
    first = result["windows"][0]
    assert first["checkpoint"] == 1
    assert first["after"].startswith("say (user=1, text=go)")
    assert first["differences"]["variables"] == ["v on user:1: python 3 turbo 4"]
    assert first["differences"]["messages"] == ["turbo only: 'hi'"]


def test_a_missing_or_failed_turbo_run_is_said() -> None:
    assert behaviour._compare(scenario(POINT), None)["status"] == "not run"
    assert behaviour._compare(scenario(POINT), {"error": "boom"})["status"] == "error"


def test_a_room_where_nothing_happens_is_told_apart() -> None:
    assert not behaviour._changes(scenario(POINT, POINT))
    assert behaviour._changes(scenario(POINT, POINT | {"users": {"1": [2, 0]}}))


def with_boxes(*boxes: dict) -> dict:
    return scenario(POINT) | {"boxes": [{"variables": [], "string": ""} | b for b in boxes]}


def differing(*categories: str) -> dict:
    return {"status": "differs", "windows": [{"differences": dict.fromkeys(categories, ["x"])}]}


def test_turbo_is_the_reference_for_built_in_variables_and_placeholders() -> None:
    built_in = with_boxes({"variables": ["-230"]})
    placeholder = with_boxes({"string": "at $(x)"})

    assert behaviour._turbo_is_reference(built_in, differing("users", "messages"))
    assert behaviour._turbo_is_reference(placeholder, differing("messages"))
    # A placeholder alone does not make a moved user Turbo's call, and a room with neither is unexplained.
    assert not behaviour._turbo_is_reference(placeholder, differing("users"))
    assert not behaviour._turbo_is_reference(with_boxes({"variables": ["=points"]}), differing("variables"))


def test_a_time_utility_sub_variable_is_named_by_its_variable_and_field() -> None:
    names = {"900001": "on_duty"}
    assert behaviour._variable_ids(["900001", "s900001-13-11", "s900001-13", "-3", "s7-1-11"], names) == [
        "=on_duty",
        "=on_duty.second",
        "=on_duty.milliseconds_of_seconds",
        "-3",
        "s7-1-11",
    ]


def test_the_room_grows_to_hold_furni_off_its_floor() -> None:
    document = {"room": {"width": 20, "height": 20}, "furni": [{"x": 39, "y": 0}], "avatars": []}
    assert behaviour._room_size(document) == (40, 20)


def test_a_known_cause_is_found_by_test_name() -> None:
    cause = behaviour._known_cause(
        "backend/tests/test_engine.py::test_value_can_come_from_another_variable#0"
    )
    assert cause == behaviour.PYTHON_IGNORES_HAS_VALUE
    assert behaviour._known_cause("backend/tests/test_engine.py::test_something_else#0") is None
