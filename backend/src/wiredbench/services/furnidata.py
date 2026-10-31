"""Turns raw furnidata into catalogue rows, and compares two versions. No I/O."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

# Classnames become file names and URLs, so anything else is skipped. Real ones include post.it and name*3.
CLASSNAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_*.-]{0,159}")
WIRED_TYPE_TOKEN = re.compile(r"(?:^|_)(trg|act|cnd|slc|xtra|var)(?:_|$)")
WIRED_TYPES = {
    "trg": "trigger",
    "act": "effect",
    "cnd": "condition",
    "slc": "selector",
    "xtra": "addon",
    "var": "variable",
}
# WIRED that a wf_ prefix check would miss.
EXTRA_WIRED = {"conf_wired_disable"}


class InvalidFurnidata(Exception):
    pass


class _Entry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: StrictInt
    classname: str
    revision: StrictInt


class _Types(BaseModel):
    furnitype: list[dict[str, Any]]


class _File(BaseModel):
    roomitemtypes: _Types
    wallitemtypes: _Types


def classify_wired(classname: str) -> tuple[bool, str | None]:
    if classname in EXTRA_WIRED:
        return True, "utility"
    if not classname.startswith("wf_"):
        return False, None
    match = WIRED_TYPE_TOKEN.search(classname[3:])
    return True, WIRED_TYPES[match.group(1)] if match else "utility"


def release_stage(classname: str, entry: dict[str, Any]) -> str:
    """A candidate signal only: an item with no offer may also be retired or event-only."""
    is_wired, _ = classify_wired(classname)
    if not is_wired:
        return "live"
    offer = entry.get("offerid")
    no_offer = isinstance(offer, int) and offer <= 0 and not entry.get("bc")
    placeholder = entry.get("name") == f"{classname} name"
    return "not_in_catalogue" if no_offer or placeholder else "live"


def _text(value: Any, limit: int = 255) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _dim(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


@dataclass
class Parsed:
    items: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0

    @property
    def wired_count(self) -> int:
        return sum(1 for item in self.items if item["is_wired"])


def parse(raw: bytes) -> Parsed:
    """Validates the whole file before anything is stored. Raises InvalidFurnidata."""
    try:
        document = _File.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise InvalidFurnidata("The file is not valid furnidata.") from exc

    parsed = Parsed()
    seen: set[str] = set()
    for kind, group in (("floor", document.roomitemtypes), ("wall", document.wallitemtypes)):
        for raw_entry in group.furnitype:
            try:
                entry = _Entry.model_validate(raw_entry)
            except ValidationError:
                parsed.skipped += 1
                continue
            name = entry.classname
            if not CLASSNAME.fullmatch(name) or ".." in name or name in seen:
                parsed.skipped += 1
                continue
            seen.add(name)
            is_wired, wired_type = classify_wired(name)
            height = raw_entry.get("height")
            parsed.items.append(
                {
                    "classname": name,
                    "kind": kind,
                    "furni_id": entry.id,
                    "revision": entry.revision,
                    "name": _text(raw_entry.get("name")),
                    "description": _text(raw_entry.get("description"), 4000),
                    "category": _text(raw_entry.get("category"), 64),
                    "furniline": _text(raw_entry.get("furniline"), 64),
                    "xdim": _dim(raw_entry.get("xdim")),
                    "ydim": _dim(raw_entry.get("ydim")),
                    "height": float(height) if isinstance(height, int | float) else None,
                    "is_wired": is_wired,
                    "wired_type": wired_type,
                    "release_stage": release_stage(name, raw_entry),
                    "data": raw_entry,
                }
            )
    if not parsed.items:
        raise InvalidFurnidata("The file has no usable furni.")
    return parsed


CHANGE_ORDER = {"new": 0, "changed": 1, "removed": 2}


def diff(old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Differences by classname, because furni IDs differ between hotels and can change. WIRED come first."""
    entries: list[dict[str, Any]] = []
    for classname in old.keys() | new.keys():
        before, after = old.get(classname), new.get(classname)
        if before == after:
            continue
        fields: list[dict[str, Any]] = []
        if before is None:
            change = "new"
        elif after is None:
            change = "removed"
        else:
            change = "changed"
            for key in sorted(before.keys() | after.keys()):
                if before.get(key) != after.get(key):
                    fields.append({"field": key, "old": before.get(key), "new": after.get(key)})
        is_wired, wired_type = classify_wired(classname)
        entries.append(
            {
                "classname": classname,
                "change": change,
                "is_wired": is_wired,
                "wired_type": wired_type,
                "name": _text((after or before or {}).get("name")),
                "fields": fields,
            }
        )
    entries.sort(key=lambda e: (not e["is_wired"], CHANGE_ORDER[e["change"]], e["classname"]))
    return entries


def summarise(entries: list[dict[str, Any]]) -> dict[str, int]:
    summary = {f"{scope}_{change}": 0 for scope in ("wired", "other") for change in CHANGE_ORDER}
    for entry in entries:
        summary[f"{'wired' if entry['is_wired'] else 'other'}_{entry['change']}"] += 1
    return summary
