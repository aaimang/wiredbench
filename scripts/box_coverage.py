#!/usr/bin/env python3
"""Updates the coverage tracker from local evidence. It only ever adds evidence, and never removes a room check.

uv run python scripts/box_coverage.py --furnidata FILE [--presets DIR] [--reference DIR --reference-commit SHA]
    [--room CLASSNAME --date YYYY-MM-DD]

Reference files and presets stay outside this repository. Only classnames and yes or no answers are stored.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TRACKER = Path(__file__).parents[1] / "backend/src/wiredbench/engine/box_coverage.json"
WF = re.compile(r"wf_[a-z_0-9]+")


def furnidata_names(path: Path) -> set[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw["roomitemtypes"]["furnitype"] + raw["wallitemtypes"]["furnitype"]
    return {str(item.get("classname", "")).split("*")[0] for item in items} - {""}


def preset_names(folder: Path) -> set[str]:
    found: set[str] = set()
    for path in folder.glob("*.json"):
        preset = json.loads(path.read_text(encoding="utf-8"))
        classes = {item["id"]: item["className"] for item in preset.get("furni", [])}
        for section in preset.get("wired", {}).values():
            if isinstance(section, list):
                found |= {classes[box["wiredId"]] for box in section if box.get("wiredId") in classes}
    return found


def reference_names(folder: Path) -> set[str]:
    return {name for path in folder.glob("*.ts") for name in WF.findall(path.read_text(encoding="utf-8"))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--furnidata", type=Path)
    parser.add_argument("--presets", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-commit")
    parser.add_argument("--room", action="append", default=[])
    parser.add_argument("--date")
    args = parser.parse_args()
    if args.room and not args.date:
        parser.error("--room needs --date")

    data = json.loads(TRACKER.read_text(encoding="utf-8")) if TRACKER.exists() else {"boxes": {}}
    boxes = data["boxes"]
    if args.furnidata:
        for name in furnidata_names(args.furnidata):
            if name.startswith("wf_"):
                boxes.setdefault(name, {})
        data["furnidata_checked_on"] = args.date or data.get("furnidata_checked_on")
    if args.presets:
        for name in preset_names(args.presets) & set(boxes):
            boxes[name]["preset"] = True
    if args.reference:
        for name in reference_names(args.reference) & set(boxes):
            boxes[name]["reference"] = True
        data["reference_commit"] = args.reference_commit
    for name in args.room:
        boxes.setdefault(name, {})["room"] = args.date
    data["boxes"] = dict(sorted(boxes.items()))
    TRACKER.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
