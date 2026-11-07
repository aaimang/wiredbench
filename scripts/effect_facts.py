#!/usr/bin/env python3
"""Lists which avatar effects can be drawn, from Habbo's own effect files. Only effect IDs are kept.

uv run python scripts/effect_facts.py --cache DIR

DIR keeps the downloaded effect files between runs, outside this repository. Run it again when Habbo
adds effects. An effect missing from the list is not marked either way.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from wiredbench.services import effects, swf
from wiredbench.services.handitems import client_folder
from wiredbench.services.upstream import Upstream

FACTS = Path(__file__).parents[1] / "backend/src/wiredbench/services/effect_facts.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--hotel", default="com")
    args = parser.parse_args()
    upstream = Upstream(httpx.HTTPTransport())
    base, build = client_folder(upstream, args.hotel)
    found = effects.parse_map(upstream.get(f"{base}effectmap.xml", effects.MAX_MAP_BYTES).body)
    args.cache.mkdir(parents=True, exist_ok=True)
    drawn = []
    for effect, lib in sorted(found.items()):
        path = args.cache / f"{lib}.swf"
        if not path.exists():
            time.sleep(0.25)  # Gentle on Habbo: one file at a time.
            fetched = upstream.get(f"{base}{lib}.swf", effects.MAX_EFFECT_BYTES)
            if fetched.status != 200:
                print(f"{effect} {lib}: HTTP {fetched.status}")
                continue
            path.write_bytes(fetched.body)
        try:
            manifest, _ = effects.build(path.read_bytes(), lib)
        except swf.SwfError as exc:
            print(f"{effect} {lib}: {exc}")
            continue
        if manifest["drawable"]:
            drawn.append(effect)
    FACTS.write_text(
        json.dumps({"checked_build": build, "checked": sorted(found), "drawn": drawn}) + "\n",
        encoding="utf-8",
    )
    print(f"{len(drawn)} of {len(found)} effects can be drawn")


if __name__ == "__main__":
    main()
