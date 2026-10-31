"""Spike: load, check, renumber and re-save G-Presets JSON without losing anything.

Everything is kept as plain data on purpose: fields we do not understand must survive a round trip.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

WIRED_SECTIONS = ("triggers", "conditions", "effects", "addons", "selectors", "variables")
ID_LIST_FIELDS = ("items", "secondItems")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(preset: dict) -> str:
    return json.dumps(preset, ensure_ascii=False, indent=2, sort_keys=True)


def wired_boxes(preset: dict) -> list[tuple[str, dict]]:
    wired = preset.get("wired", {})
    return [(section, box) for section in WIRED_SECTIONS for box in wired.get(section, [])]


def check(preset: dict, known_classnames: set[str]) -> list[str]:
    """Return problems that would stop a preset being trusted or imported."""
    problems = []
    furni = preset.get("furni", [])
    ids = [f["id"] for f in furni]
    for furni_id, count in Counter(ids).items():
        if count > 1:
            problems.append(f"duplicate furni id {furni_id}")
    id_set = set(ids)
    for item in furni:
        if item["className"] not in known_classnames:
            problems.append(f"unknown classname {item['className']}")
    for section, box in wired_boxes(preset):
        if box["wiredId"] not in id_set:
            problems.append(f"{section} wiredId {box['wiredId']} has no furni")
        for field in ID_LIST_FIELDS:
            for ref in box.get(field, []):
                if ref not in id_set:
                    problems.append(f"{section} wiredId {box['wiredId']} {field} -> missing {ref}")
    for binding in preset.get("bindings", []):
        if binding["wiredId"] not in id_set or binding["furniId"] not in id_set:
            problems.append(f"binding {binding} points at a missing furni")
    return problems


def renumber(preset: dict, start: int = 1000) -> dict:
    """Give furni new ids and fix every known reference, as an import must."""
    out = copy.deepcopy(preset)
    mapping = {f["id"]: start + i for i, f in enumerate(out.get("furni", []))}
    for item in out.get("furni", []):
        item["id"] = mapping[item["id"]]
        if "name" in item:
            item["name"] = f"{item['className']}[{item['id']}]"
    for _, box in wired_boxes(out):
        box["wiredId"] = mapping.get(box["wiredId"], box["wiredId"])
        for field in ID_LIST_FIELDS:
            if field in box:
                box[field] = [mapping.get(r, r) for r in box[field]]
    for binding in out.get("bindings", []):
        binding["wiredId"] = mapping.get(binding["wiredId"], binding["wiredId"])
        binding["furniId"] = mapping.get(binding["furniId"], binding["furniId"])
    return out


def shape(preset: dict) -> list:
    """Id-independent fingerprint: each box by classname, with references resolved to classnames."""
    classes = {f["id"]: f["className"] for f in preset.get("furni", [])}
    rows = []
    for section, box in wired_boxes(preset):
        row = {k: v for k, v in box.items() if k not in ("wiredId", *ID_LIST_FIELDS)}
        row["_section"] = section
        row["_class"] = classes.get(box["wiredId"])
        for field in ID_LIST_FIELDS:
            row[field] = sorted(classes.get(r, str(r)) for r in box.get(field, []))
        rows.append(json.dumps(row, sort_keys=True, ensure_ascii=False))
    return sorted(rows)
