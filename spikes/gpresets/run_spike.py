"""Spike runner. Usage: run_spike.py <presets_dir> <furnidata.json>"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gpreset  # noqa: E402


def main() -> None:
    presets_dir, furnidata = Path(sys.argv[1]), Path(sys.argv[2])
    raw = json.loads(furnidata.read_text())
    items = raw["roomitemtypes"]["furnitype"] + raw["wallitemtypes"]["furnitype"]
    known = {x["classname"] for x in items if x.get("classname")}

    for path in sorted(presets_dir.glob("*.json")):
        preset = gpreset.load(path)
        again = json.loads(gpreset.dump(preset))
        boxes = gpreset.wired_boxes(preset)
        if "furni" not in preset:
            print(f"== {path.name}\n partial file, keys: {sorted(preset)} wired: {sorted(preset['wired'])} lossless: {again == preset}")
            continue
        classes = {f["id"]: f["className"] for f in preset["furni"]}
        moved = gpreset.renumber(preset)

        print(f"== {path.name}")
        print(" top-level keys:", sorted(preset))
        print(" furni:", len(preset["furni"]), "bindings:", len(preset.get("bindings", [])))
        print(" sections:", {k: len(v) for k, v in preset["wired"].items()})
        print(" box fields:", dict(Counter(k for _, b in boxes for k in b)))
        print(" furni fields:", dict(Counter(k for f in preset["furni"] for k in f)))
        print(" wired classes:", dict(Counter(classes.get(b["wiredId"], "?") for _, b in boxes)))
        print(" variables_map entries:", len(preset["wired"].get("variables_map") or {}))
        print(" problems:", gpreset.check(preset, known)[:10])
        print(" lossless round trip:", again == preset)
        print(" renumber keeps structure:", gpreset.shape(moved) == gpreset.shape(preset))
        print(" renumbered problems:", gpreset.check(moved, known)[:10])
        print(" opaque references kept (not remapped):", dict(Counter(
            k for _, b in boxes for k in ("furniSources", "userSources", "variableIds", "variableId") if b.get(k)
        )))


if __name__ == "__main__":
    main()
