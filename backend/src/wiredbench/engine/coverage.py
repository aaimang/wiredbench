"""How far each WIRED box's options have been checked, and with what evidence.

Evidence climbs one way: nothing, a reference, a real preset file, a dump of real boxes, then a room check. A dump
shows a box's real settings and defaults, but not what its numbers mean or what it does when it runs. A form or an
option mapping says what Wiredbench can do with a box, not whether that matches Habbo, so they are shown apart.
"""

from __future__ import annotations

import json
from collections import Counter
from importlib import resources
from typing import Any

from wiredbench.engine.boxes import BOXES
from wiredbench.services.exchange import OPTION_FIELDS

LEVELS = ("unknown", "from_reference", "real_preset", "real_dump", "real_room")


def load() -> dict[str, Any]:
    text = resources.files("wiredbench.engine").joinpath("box_coverage.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def level(entry: dict[str, Any]) -> str:
    if entry.get("room"):
        return "real_room"
    if entry.get("dump"):
        return "real_dump"
    if entry.get("preset"):
        return "real_preset"
    return "from_reference" if entry.get("reference") else "unknown"


def room_checked() -> set[str]:
    return {name for name, entry in load()["boxes"].items() if entry.get("room")}


def rows() -> list[dict[str, Any]]:
    return [
        {
            "classname": name,
            "evidence": level(entry),
            "room_checked_on": entry.get("room"),
            "has_form": name in BOXES,
            "options_mapped": name in OPTION_FIELDS,
            "note": entry.get("note", ""),
        }
        for name, entry in sorted(load()["boxes"].items())
    ]


def summary() -> dict[str, int]:
    all_rows = rows()
    counts = Counter(row["evidence"] for row in all_rows)
    return {
        "total": len(all_rows),
        **{name: counts[name] for name in LEVELS},
        "has_form": sum(row["has_form"] for row in all_rows),
        "options_mapped": sum(row["options_mapped"] for row in all_rows),
    }
