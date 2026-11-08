#!/usr/bin/env python3
"""Lists the hand items each vending furni gives, from a retro server's base database dump.

uv run python scripts/vending_facts.py --sql PATH

PATH is a SQL dump with an `items_base` table, kept outside this repository. Only furni whose
interaction is a vending machine are kept, as their class name and hand item IDs. Habbo's furnidata
does not carry these, so a furni missing from the list gives nothing in Wiredbench.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FACTS = Path(__file__).parents[1] / "backend/src/wiredbench/engine/vending_facts.json"
ROW = re.compile(r"^INSERT INTO `items_base` \((?P<cols>[^)]*)\) VALUES \((?P<vals>.*)\);$")
VALUE = re.compile(r"'((?:[^'\\]|\\.)*)'|([^,\s][^,]*)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", type=Path, required=True)
    args = parser.parse_args()
    found: dict[str, list[int]] = {}
    with args.sql.open(encoding="utf-8", errors="replace") as dump:
        for line in dump:
            match = ROW.match(line.strip())
            if not match:
                continue
            cols = [col.strip(" `") for col in match["cols"].split(",")]
            vals = [quoted or bare for quoted, bare in VALUE.findall(match["vals"])]
            row = dict(zip(cols, vals, strict=False))
            if row.get("interaction_type") != "vendingmachine":
                continue
            ids = sorted(
                {int(part) for part in row.get("vending_ids", "").split(",") if part.strip().isdigit()}
            )
            ids = [i for i in ids if i > 0]
            if ids:
                found[row["item_name"]] = ids
    FACTS.write_text(json.dumps({"furni": dict(sorted(found.items()))}, indent=None) + "\n", encoding="utf-8")
    print(f"{len(found)} vending furni written to {FACTS.name}")


if __name__ == "__main__":
    main()
