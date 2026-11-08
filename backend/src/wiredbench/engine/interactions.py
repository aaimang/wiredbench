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


def entered_from_front(kind: Kind) -> bool:
    """Teleports and one-way gates are used from the tile in front of them."""
    return kind in ("teleport", "one_way_gate")


def needs_to_be_next_to(kind: Kind) -> bool:
    """Whether the user must stand on a tile next to it. The floor switch's own text says so."""
    return kind in ("dice", "switch")


def next_to(user: tuple[int, int], item: tuple[int, int]) -> bool:
    """On one of the eight tiles around a furni's tile."""
    return max(abs(user[0] - item[0]), abs(user[1] - item[1])) == 1


# A teleport's sequence, from stepping in to stepping out of its partner. Assumed timings, not measured
# in a real room yet. States from the teleport's art: 0 closed, 1 open, 2 teleporting.
TELEPORT_OPEN, TELEPORT_FLASH = 1, 2
TELEPORT_FLASH_AT_MS = 500
TELEPORT_ARRIVE_AT_MS = 1500
TELEPORT_OUT_AT_MS = 2000
TELEPORT_CLOSE_AT_MS = 2500
# A one-way gate opens, lets the user through and closes. Assumed timings.
ONE_WAY_THROUGH_MS = 500
ONE_WAY_CLOSE_MS = 1000

# A furni's front, by its rotation: the tile a teleport or one-way gate is entered from.
_FRONT = {0: (0, -1), 2: (1, 0), 4: (0, 1), 6: (-1, 0)}


def front_of(x: int, y: int, rot: int) -> tuple[int, int]:
    dx, dy = _FRONT.get(rot % 8, (0, 1))
    return x + dx, y + dy


def back_of(x: int, y: int, rot: int) -> tuple[int, int]:
    dx, dy = _FRONT.get(rot % 8, (0, 1))
    return x - dx, y - dy
