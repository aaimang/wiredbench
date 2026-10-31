"""Spike runner: download furni SWFs, render them, and report a success rate.

Usage: run_spike.py <furnidata.json> <download_dir> <output_dir> [random_sample_size]
"""

from __future__ import annotations

import json
import random
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import swf_furni  # noqa: E402

UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"
SHOWCASE = [
    "wf_act_move_rotate", "wf_trg_state_changed", "wf_xtra_anim_time", "wf_var_user",
    "wf_antenna1", "wf_arrowplate", "wf_floor_switch1", "wf_tile1", "wf_colortile",
    "wf_button", "wf_glowball", "wf_label", "wf_fx_firegate", "wf_test_act",
    "shelves_norja", "throne",
]


def fetch(item: dict, dest: Path) -> bytes:
    base = item["classname"].split("*")[0]
    path = dest / f"{item['revision']}_{base}.swf"
    if path.exists():
        return path.read_bytes()
    url = f"https://images.habbo.com/dcr/hof_furni/{item['revision']}/{base}.swf"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = res.read(swf_furni.MAX_SWF_BYTES + 1)
    path.write_bytes(data)
    time.sleep(0.05)
    return data


def main() -> None:
    furnidata, downloads, output = map(Path, sys.argv[1:4])
    sample_size = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    downloads.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    raw = json.loads(furnidata.read_text())
    floor = raw["roomitemtypes"]["furnitype"]
    by_class = {x["classname"]: x for x in floor if x.get("classname")}

    random.seed(20261031)
    wired = [x for x in floor if x["classname"].startswith("wf_")]
    others = random.sample([x for x in floor if x.get("classname") and not x["classname"].startswith("wf_")], sample_size)
    others += [by_class[n] for n in SHOWCASE if n in by_class and not n.startswith("wf_")]

    stats = Counter()
    failures = []
    unsupported = Counter()
    sheet_items = []
    slowest = 0.0
    for item in wired + others:
        group = "wired" if item["classname"].startswith("wf_") else "other"
        stats[f"{group}_total"] += 1
        try:
            data = fetch(item, downloads)
            started = time.perf_counter()
            swf = swf_furni.parse(data)
            sprites = swf_furni.compose(swf, item["classname"], direction=_first_dir(swf, item))
            slowest = max(slowest, time.perf_counter() - started)
            for code, count in swf.unsupported_tags.items():
                unsupported[code] += count
            if not sprites:
                raise swf_furni.SwfError("no sprites")
            stats[f"{group}_ok"] += 1
            if item["classname"] in SHOWCASE:
                sheet_items.append((item["classname"], swf_furni.render(sprites)))
        except Exception as exc:  # A spike wants every failure counted, not the first one raised.
            failures.append((item["classname"], type(exc).__name__, str(exc)[:90]))

    for name in SHOWCASE:
        if name in by_class and not any(n == name for n, _ in sheet_items):
            failures.append((name, "showcase", "not rendered"))

    # Multi-direction and multi-state proof on one item.
    extras = []
    switch = by_class.get("wf_floor_switch1")
    if switch:
        swf = swf_furni.parse(fetch(switch, downloads))
        for state in (0, 1):
            extras.append((f"switch state {state}", swf_furni.render(swf_furni.compose(swf, "wf_floor_switch1", state=state))))
    throne = by_class.get("throne")
    if throne:
        swf = swf_furni.parse(fetch(throne, downloads))
        for d in swf_furni.directions_of(swf, "throne"):
            extras.append((f"throne dir {d}", swf_furni.render(swf_furni.compose(swf, "throne", direction=d))))

    tiles = sheet_items + extras
    cols, cell = 6, 200
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell, rows * (cell + 18)), (244, 239, 230, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, image) in enumerate(tiles):
        x, y = (i % cols) * cell, (i // cols) * (cell + 18)
        sheet.alpha_composite(image.crop((28, 28, 228, 228)), dest=(x, y))
        draw.text((x + 4, y + cell + 2), name, fill=(38, 33, 28, 255))
    sheet.save(output / "contact_sheet.png")

    result = {
        "stats": dict(stats),
        "slowest_parse_seconds": round(slowest, 3),
        "unsupported_tags": dict(unsupported),
        "failures": failures,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "failures"}, indent=2))
    print("failures:", len(failures))
    for failure in failures[:25]:
        print(" ", failure)


def _first_dir(swf: swf_furni.FurniSwf, item: dict) -> int:
    dirs = swf_furni.directions_of(swf, item["classname"])
    if not dirs:
        return 2
    return 2 if 2 in dirs else dirs[0]


if __name__ == "__main__":
    main()
