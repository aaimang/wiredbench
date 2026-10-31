#!/usr/bin/env python3
"""Derives box facts from a local dump of real WIRED boxes, keeping nothing tied to one room.

uv run python scripts/box_facts.py --dump FILE

The dump stays outside this repository. Positions, IDs, picks, variable data and raw packets are never copied.
Boxes in a dump are unedited, so numbers are defaults, and no labels come with them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FACTS = Path(__file__).parents[1] / "backend/src/wiredbench/engine/box_facts.json"
COPIED = (
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
)
DEFAULTS_BY_SECTION = ("quantifier", "filter")


def derive(dump: dict[str, Any]) -> dict[str, Any]:
    boxes: dict[str, Any] = {}
    no_reply: list[str] = []
    for box in dump["boxes"]:
        name = box["classname"]
        if box.get("not_read"):
            no_reply.append(name)
            continue
        fact = {key: box[key] for key in COPIED}
        fact["has_delay"] = "delay" in box
        fact["variable_slots"] = len(box.get("variable_ids", []))
        for key in DEFAULTS_BY_SECTION:
            if key in box:
                fact[key] = box[key]
        if "invert" in box:
            fact["invert"] = box["invert"]
        if box.get("context_error"):
            fact["context_unread"] = True
        boxes[name] = fact
    return {
        "capture": {
            "date": str(dump["captured_at"])[:10],
            "build": dump["hotel_version"],
            "boxes_unedited": True,
        },
        "no_reply": sorted(no_reply),
        "boxes": dict(sorted(boxes.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True)
    args = parser.parse_args()
    facts = derive(json.loads(args.dump.read_text(encoding="utf-8")))
    FACTS.write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
