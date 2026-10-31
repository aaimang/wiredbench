#!/usr/bin/env python3
"""Writes a preset with unusual option values, and a checklist of what each box should show in a real room.

uv run python scripts/proof_preset.py --group triggers --out proof-triggers
Import the JSON, open each box, and compare it with the Markdown. Then record each match with box_coverage.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from wiredbench.engine.boxes import BOXES
from wiredbench.services.exchange import OPTION_FIELDS, export_gpresets, section_of

COLUMNS = 8
UNUSUAL_NUMBER = 7


def unusual(field: dict[str, Any], reader: Any) -> Any:
    """A valid value that differs from the default, so a box left at its default shows up as a failure."""
    if field["kind"] == "bool":
        return not field["default"]
    if field["kind"] == "select":
        return next(option for option in reversed(field["options"]) if option != field["default"])
    if field["kind"] == "number":
        if isinstance(reader, int | float) and not isinstance(reader, bool):
            return round(
                UNUSUAL_NUMBER * reader, 3
            )  # Units of half seconds and the like must land on a whole number.
        return min(field.get("max", field["default"] + 3), field["default"] + 3)
    return field["default"]


def build(group: str) -> tuple[dict[str, Any], dict[str, Any]]:
    furni: list[dict[str, Any]] = []
    expected: dict[str, Any] = {}
    names = sorted(name for name in OPTION_FIELDS if group == "all" or section_of(name) == group)
    for index, classname in enumerate(names):
        fields = {field["name"]: field for field in BOXES[classname]["fields"]}
        settings = {name: unusual(fields[name], reader) for name, _, reader in OPTION_FIELDS[classname]}
        if "text" in fields:
            settings["text"] = "proof"
        if classname.startswith("wf_var_"):
            settings["variable"] = f"proof_{classname.removeprefix('wf_var_')}"
        furni_id = index + 1
        x, y = index % COLUMNS, index // COLUMNS
        furni.append(
            {
                "id": furni_id,
                "classname": classname,
                "x": x,
                "y": y,
                "z": 0,
                "rot": 0,
                "state": 0,
                "wired": settings,
            }
        )
        expected[classname] = {"tile": [x, y], "settings": settings}
    preset, _ = export_gpresets({"furni": furni, "avatars": []})
    return preset, expected


def checklist(group: str, expected: dict[str, Any]) -> str:
    lines = [
        f"# Proof checklist: {group}",
        "",
        "Open each box and compare. A box that differs did not pass.",
        "",
    ]
    for classname, item in expected.items():
        x, y = item["tile"]
        lines.append(f"- [ ] `{classname}` at {x}, {y}")
        lines += [f"  - {name}: {value}" for name, value in item["settings"].items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="all")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    preset, expected = build(args.group)
    if not expected:
        raise SystemExit(f"No mapped boxes in group {args.group}.")
    args.out.with_suffix(".json").write_text(json.dumps(preset, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(checklist(args.group, expected), encoding="utf-8")


if __name__ == "__main__":
    main()
