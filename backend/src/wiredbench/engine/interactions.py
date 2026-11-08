"""How each kind of furni reacts when a user uses it, as in a real room.

Habbo's server decides who may use a furni (its usage policy) and what using it does. That is not in
any public file, so furni are sorted into kinds by their name and catalogue category. Rules marked
"assumed" have not been checked in a real room yet.
"""

from __future__ import annotations

from typing import Literal

Kind = Literal["dice", "switch", "teleport", "gate", "one_way_gate", "vending", "default"]

# How long a dice shows its rolling animation before landing. Assumed, not measured in a real room.
DICE_ROLL_MS = 1500
DICE_FACES = (1, 2, 3, 4, 5, 6)
DICE_CLOSED = 0
DICE_ROLLING = -1


def kind_of(classname: str, category: str | None) -> Kind:
    """A furni's interaction kind, from its name and its furnidata category."""
    name = classname.lower()
    if "dice" in name:
        return "dice"
    if name.startswith("wf_floor_switch"):
        return "switch"
    if name.startswith("one_way_door"):
        return "one_way_gate"
    if category == "teleport":
        return "teleport"
    if category == "gate":
        return "gate"
    if category == "vending_machine":
        return "vending"
    return "default"


def anyone_may_use(kind: Kind) -> bool:
    """Whether a user without rights may use it. Most furni switch only for the owner or rights."""
    return kind in ("dice", "switch", "teleport", "one_way_gate", "vending")


def needs_to_be_next_to(kind: Kind) -> bool:
    """Whether the user must stand on a tile next to it. The floor switch's own text says so."""
    return kind in ("dice", "switch")


def next_to(user: tuple[int, int], item: tuple[int, int]) -> bool:
    """On one of the eight tiles around a furni's tile."""
    return max(abs(user[0] - item[0]), abs(user[1] - item[1])) == 1
