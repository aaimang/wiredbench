"""Change Variable Value's operations, including the edges of a 64-bit value."""

from __future__ import annotations

import random

import pytest

from wiredbench.engine.boxes import BOXES
from wiredbench.engine.operations import OPERATION_CODES, OPERATION_LABELS, apply

MAX = 2**63 - 1
MIN = -(2**63)


@pytest.mark.parametrize(
    ("operation", "current", "operand", "expected"),
    [
        ("set", 3, 7, 7),
        ("add", 3, 7, 10),
        ("subtract", 3, 7, -4),
        ("multiply", 3, 7, 21),
        ("divide", 7, 2, 3),
        ("divide", -7, 2, -3),
        ("divide", 2**62 + 1, 1, 2**62 + 1),
        ("divide", 10, 0, MAX),
        ("divide", -10, 0, MIN),
        ("divide", 0, 0, 0),
        ("divide", MIN, -1, MIN),
        ("power", 2, 40, 2**40),
        ("power", 2, 63, MIN),
        ("power", 2, 64, 0),
        ("power", 2, -1, 1),
        ("modulo", 7, 3, 1),
        ("modulo", -7, 3, -1),
        ("modulo", 7, 0, 0),
        ("modulo", MIN, -1, 0),
        ("set_minimum", 3, 7, 7),
        ("set_maximum", 3, 7, 3),
        ("random", 3, 0, 0),
        ("random", 3, -5, 0),
        ("absolute", -3, 0, 3),
        ("absolute", MIN, 0, MIN),
        ("bit_and", 6, 3, 2),
        ("bit_or", 6, 3, 7),
        ("bit_xor", 6, 3, 5),
        ("invert", 6, 0, -7),
        ("shift_left", 1, 3, 8),
        ("shift_left", 1, 99, MIN),
        ("shift_right", 8, 3, 1),
        ("shift_right", -1, 60, 15),
        ("bit_count", 7, 0, 3),
        ("bit_count", -1, 0, 64),
        ("next_low", 3, 0, 2),
        ("next_high", 4, 0, 2),
        ("next_high", 0, 0, -1),
        ("previous_low", 3, 3, 3),
        ("previous_high", 4, 63, 2),
        ("next_low_after", 1, 0, 1),
        ("next_high_after", 5, 0, 2),
        ("previous_low_before", 2, 2, 0),
        ("previous_high_before", 5, 2, 0),
        ("get_bit", 4, 2, 1),
        ("get_bit", 4, 64, 0),
        ("set_bit", 0, 63, MIN),
        ("set_bit", 5, -1, 5),
        ("clear_bit", 5, 0, 4),
        ("toggle_bit", 5, 1, 7),
    ],
)
def test_operations(operation: str, current: int, operand: int, expected: int) -> None:
    assert apply(operation, current, operand, random.Random(1)) == expected  # noqa: S311


def test_random_is_in_range_and_follows_the_seed() -> None:
    first = [apply("random", 0, 5, rng) for rng in [random.Random(1)] * 200]  # noqa: S311
    again = [apply("random", 0, 5, rng) for rng in [random.Random(1)] * 200]  # noqa: S311
    assert set(first) == set(range(6))
    assert first == again


def test_every_operation_has_a_number_a_label_and_a_form_option() -> None:
    assert set(OPERATION_CODES.values()) == set(OPERATION_LABELS)
    field = next(f for f in BOXES["wf_act_change_var_val"]["fields"] if f["name"] == "operation")
    assert field["options"] == list(OPERATION_LABELS)
