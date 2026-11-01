#!/usr/bin/env python3
"""Writes the internal variable facts from a real room dump. Only names, IDs, flags and the names a value stands for are kept.

uv run python scripts/internal_variables.py DUMP.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).parents[1] / "backend/src/wiredbench/engine/internal_variables.json"
TARGETS = {0: "furni", 1: "user", -10: "global", -20: "context"}


def main() -> None:
    dump = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "target": TARGETS[row["variable_type"]],
            "has_value": row["has_value"],
            "can_write": row["can_write_value"],
            "always_available": row["always_available"],
            **({"text_connector": row["text_connector"]} if row.get("text_connector") else {}),
        }
        for row in dump["variables"]
        if str(row["name"]).startswith(("@", "~"))
    ]
    rows.sort(key=lambda row: (row["target"], row["name"]))
    OUT.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    print(len(rows))


if __name__ == "__main__":
    main()
