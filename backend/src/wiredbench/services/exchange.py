"""Reads and writes room files: Wiredbench's own format, and the G-Presets JSON format.

G-Presets fields are mostly undocumented, so each imported item keeps its original data. Export starts
from that data and changes only what was edited, which means fields this code cannot read survive.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from wiredbench.engine.boxes import BOXES
from wiredbench.errors import ApiError
from wiredbench.services.room import MAX_ROOM_SIZE, MAX_Z

NATIVE_FORMAT = "wiredbench"
NATIVE_VERSION = 1
SECTIONS = {
    "wf_trg_": "triggers",
    "wf_cnd_": "conditions",
    "wf_act_": "effects",
    "wf_slc_": "selectors",
    "wf_xtra_": "addons",
    "wf_var_": "variables",
}
MIN_ROOM = 12
NEW_VARIABLE_ID = 900_000
# Values seen in real preset files. A new box of any other type is exported with empty options and a warning.
KNOWN_BOXES: dict[str, dict[str, Any]] = {
    "wf_trg_click_furni": {"options": [], "furniSources": [100]},
    "wf_trg_state_changed": {"options": [], "furniSources": [100]},
    "wf_trg_recv_signal": {"options": [], "furniSources": [100]},
    "wf_trg_says_something": {"options": [0, 1, 1]},
    "wf_act_toggle_state": {"options": [0], "furniSources": [200]},
    "wf_act_send_signal": {"options": [0, 0], "furniSources": [100, 200], "userSources": [200]},
    "wf_act_log": {"options": [2]},
    "wf_act_give_var": {"options": [1, 0, 0, 0], "furniSources": [100], "userSources": [200]},
    "wf_act_remove_var": {"options": [1], "furniSources": [100], "userSources": [200]},
    "wf_xtra_exec_in_order": {"options": []},
    "wf_xtra_text_output_username": {"options": [0], "userSources": [0]},
    "wf_var_room": {"options": [1]},
    "wf_var_context": {"options": [1]},
    "wf_var_furni": {"options": [1, 10]},
    "wf_var_user": {"options": [10, 1]},
}


# Where each setting sits in a box's options list: (setting, position, how the number reads).
# A scale turns the number into seconds, a tuple lists names by number, and bool is 0 or 1.
OPTION_FIELDS: dict[str, list[tuple[str, int, Any]]] = {
    "wf_trg_says_something": [
        ("owner_only", 0, bool),
        ("match", 1, ("contains", "exact", "all")),
        ("hide_message", 2, bool),
    ],
    "wf_trg_periodically": [("seconds", 0, 0.5)],
    "wf_trg_period_short": [("seconds", 0, 0.05)],
    "wf_trg_period_long": [("seconds", 0, 5)],
    "wf_act_user_to_furni": [("walking", 0, ("closer", "keep", "stop"))],
    "wf_act_move_rotate": [("rotation", 1, ("none", "clockwise", "counterclockwise", "random"))],
    "wf_act_log": [("level", 0, ("0", "1", "2", "3"))],
    "wf_cnd_user_count_in": [("min", 0, int), ("max", 1, int)],
    "wf_cnd_not_user_count": [("min", 0, int), ("max", 1, int)],
    "wf_xtra_execution_limit": [("count", 0, int), ("window_seconds", 1, 0.5)],
    "wf_xtra_random": [("skip", 0, int), ("pick", 1, int)],
    "wf_xtra_filter_users": [("amount", 0, int)],
    "wf_xtra_filter_furni": [("amount", 0, int)],
    "wf_xtra_text_output_variable": [
        ("placeholder_type", 0, ("single", "multiple")),
        ("display", 2, ("numeric", "textual")),
    ],
    "wf_var_user": [
        ("availability", 0, {0: "active", 10: "persistent", 11: "shared"}),
        ("has_value", 1, bool),
    ],
    "wf_var_furni": [
        ("has_value", 0, bool),
        ("availability", 1, {0: "active", 10: "persistent", 11: "shared"}),
    ],
    "wf_var_context": [("has_value", 0, bool)],
}


def _option_to_setting(raw: Any, reader: Any) -> Any:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if reader is bool:
        return raw != 0
    if reader is int:
        return raw
    if isinstance(reader, tuple):
        return reader[raw] if 0 <= raw < len(reader) else None
    if isinstance(reader, dict):
        return reader.get(raw)
    return round(raw * reader, 3)


def _setting_to_option(value: Any, reader: Any) -> int | None:
    if reader is bool:
        return 1 if value else 0
    if reader is int:
        return int(value) if isinstance(value, int | float) else None
    if isinstance(reader, tuple):
        return reader.index(value) if value in reader else None
    if isinstance(reader, dict):
        return next((number for number, name in reader.items() if name == value), None)
    return round(value / reader) if isinstance(value, int | float) else None


def _write_option(box: dict[str, Any], position: int, number: int) -> None:
    options = box["options"] if isinstance(box.get("options"), list) else []
    box["options"] = options + [0] * (position + 1 - len(options)) if len(options) <= position else options
    box["options"][position] = number


def _invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_room_file", message)


def section_of(classname: str) -> str | None:
    return next((name for prefix, name in SECTIONS.items() if classname.startswith(prefix)), None)


def _field_names(classname: str) -> set[str]:
    spec = BOXES.get(classname)
    return {field["name"] for field in spec["fields"]} if spec else set()


def _variable_names(raw_map: Any, boxes: list[dict[str, Any]]) -> dict[str, str]:
    """Variable ID to name. IDs belong to one room, so names are what carry between rooms."""
    names = {str(value): str(name) for name, value in raw_map.items()} if isinstance(raw_map, dict) else {}
    for box in boxes:
        if "variableId" in box and isinstance(box.get("config"), str):
            names.setdefault(str(box["variableId"]), box["config"])
    return names


def friendly_settings(classname: str, box: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """The settings the engine can use. Only meanings the sample files support are read."""
    fields = _field_names(classname)
    settings: dict[str, Any] = {}
    if "delay" in fields and isinstance(box.get("delay"), int):
        settings["delay"] = box["delay"]
    items = box.get("items")
    if isinstance(items, list) and all(isinstance(item, int) for item in items):
        if "furni" in fields:
            settings["furni"] = items
        elif "antenna" in fields:
            settings["antenna"] = items
    config = box.get("config")
    if isinstance(config, str):
        for name in ("text", "placeholder"):
            if name in fields:
                settings[name] = config
    if classname.startswith("wf_var_") and isinstance(config, str):
        settings["variable"] = config
    elif "variable" in fields and isinstance(box.get("variableIds"), list) and box["variableIds"]:
        variable = names.get(str(box["variableIds"][0]))
        if variable:
            settings["variable"] = variable
    options = box.get("options")
    if isinstance(options, list):
        for name, position, reader in OPTION_FIELDS.get(classname, []):
            value = _option_to_setting(options[position], reader) if position < len(options) else None
            if value is not None:
                settings[name] = value
    return settings


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(f"This file has a furni with a bad {label}.")
    return value


def _state(raw: Any) -> int:
    try:
        return max(0, min(int(raw), 9999))
    except (TypeError, ValueError):
        return 0  # Text states are kept in the original data.


def _room_size(preset: dict[str, Any], furni: list[dict[str, Any]]) -> dict[str, int]:
    rows = preset.get("floorplan")
    lines = [line for line in rows.replace("\n", "\r").split("\r") if line] if isinstance(rows, str) else []
    width = max([MIN_ROOM, *(len(line) for line in lines), *(item["x"] + 1 for item in furni)])
    height = max([MIN_ROOM, len(lines), *(item["y"] + 1 for item in furni)])
    if width > MAX_ROOM_SIZE or height > MAX_ROOM_SIZE:
        raise _invalid(f"This room is {width} by {height}, and the largest allowed is {MAX_ROOM_SIZE}.")
    return {"width": width, "height": height}


def _read_furni(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("className"), str):
        raise _invalid("This file has a furni with no class name.")
    furni_id, location = raw.get("id"), raw.get("location")
    if isinstance(furni_id, bool) or not isinstance(furni_id, int) or furni_id < 1:
        raise _invalid("This file has a furni with a bad ID.")
    if not isinstance(location, dict):
        raise _invalid("This file has a furni with no position.")
    x, y = _number(location.get("x"), "position"), _number(location.get("y"), "position")
    z = _number(location.get("z", 0), "height")
    if (
        x != int(x)
        or y != int(y)
        or not 0 <= x < MAX_ROOM_SIZE
        or not 0 <= y < MAX_ROOM_SIZE
        or not 0 <= z <= MAX_Z
    ):
        raise _invalid(f"A furni's position is outside what a room here can hold ({raw['className']}).")
    rotation = raw.get("rotation", 0)
    return {
        "id": furni_id,
        "classname": raw["className"],
        "x": int(x),
        "y": int(y),
        "z": z,
        "rot": rotation
        if isinstance(rotation, int) and not isinstance(rotation, bool) and 0 <= rotation <= 7
        else 0,
        "state": _state(raw.get("state", 0)),
        "gpreset": raw,
    }


def import_gpresets(preset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns a room document and a report on what could be read."""
    raw_furni = preset.get("furni", [])
    wired = preset.get("wired", {})
    if not isinstance(raw_furni, list) or not isinstance(wired, dict):
        raise _invalid("This G-Presets file has the wrong shape.")
    furni = [_read_furni(raw) for raw in raw_furni]
    by_id = {item["id"]: item for item in furni}
    if len(by_id) != len(furni):
        raise _invalid("This file uses the same furni ID twice.")

    extras = {key: copy.deepcopy(value) for key, value in wired.items() if key not in SECTIONS.values()}
    sections = [key for key, value in wired.items() if key in SECTIONS.values() and isinstance(value, list)]
    boxes = [box for key in sections for box in wired[key] if isinstance(box, dict)]
    names = _variable_names(wired.get("variables_map"), boxes)
    orphans: list[dict[str, Any]] = []
    read, kept_raw = 0, Counter[str]()
    for key in sections:
        for order, box in enumerate(wired[key]):
            item = by_id.get(box.get("wiredId")) if isinstance(box, dict) else None
            if item is None or "gpreset_box" in item:
                orphans.append({"section": key, "order": order, "box": box})
                continue
            item["gpreset_box"] = {"section": key, "order": order, "box": box}
            item["wired"] = friendly_settings(item["classname"], box, names)
            if item["classname"] in BOXES:
                read += 1
            else:
                kept_raw[item["classname"]] += 1

    document: dict[str, Any] = {
        "schema": 1,
        "room": _room_size(preset, furni),
        "furni": furni,
        "avatars": [],
        "gpreset": {
            "top": {k: copy.deepcopy(v) for k, v in preset.items() if k not in ("furni", "wired")},
            "has_furni": "furni" in preset,
            "has_wired": "wired" in preset,
            "sections": sections,
            "wired_extras": extras,
            "orphans": orphans,
        },
    }
    report: dict[str, Any] = {
        "format": "gpresets",
        "furni": len(furni),
        "boxes": len(boxes),
        "partial": "furni" not in preset,
        "not_placed": len(orphans),
        "simulated": read,
        "not_simulated": dict(sorted(kept_raw.items())),
        "warnings": [],
    }
    if report["partial"]:
        report["warnings"].append("This file has WIRED settings but no furni, so the room starts empty.")
    return document, report


def _export_furni(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("gpreset")
    out: dict[str, Any] = copy.deepcopy(raw) if isinstance(raw, dict) else {"name": f"{item['classname']}[0]"}
    location: dict[str, Any] = out["location"] if isinstance(out.get("location"), dict) else {}
    for key in ("x", "y", "z"):
        if location.get(key) != item.get(key, 0):
            location[key] = item.get(key, 0)
    out.update(className=item["classname"], id=item["id"], location=location, rotation=item.get("rot", 0))
    state = item.get("state", 0)
    if _state(out.get("state", 0)) != state or (state and "state" not in out):
        out["state"] = str(state)
    return out


def _new_box(classname: str, warnings: list[str]) -> dict[str, Any]:
    known = KNOWN_BOXES.get(classname)
    if known is None and classname not in OPTION_FIELDS:
        warnings.append(f"{classname} is new here, and its options are unknown. Check it after importing.")
    box: dict[str, Any] = {
        "secondItems": [],
        "furniSources": [],
        "userSources": [],
        "variableIds": [],
        "options": [],
        "config": "",
        "items": [],
    }
    box.update(copy.deepcopy(known or {}))
    if classname.startswith("wf_act_"):
        box["delay"] = 0
    return box


def _variable_id(name: str, variables: dict[str, Any], used: list[int]) -> str:
    if name not in variables:
        used[0] += 1
        variables[name] = str(NEW_VARIABLE_ID + used[0])
    return str(variables[name])


def _default(classname: str, name: str) -> Any:
    fields = BOXES.get(classname, {}).get("fields", [])
    return next((field["default"] for field in fields if field["name"] == name), None)


def _apply_settings(
    item: dict[str, Any],
    box: dict[str, Any],
    base: dict[str, Any],
    variables: dict[str, Any],
    used: list[int],
    warnings: list[str],
) -> None:
    """Writes back only the settings that differ from what the box already said."""
    settings: dict[str, Any] = item["wired"] if isinstance(item.get("wired"), dict) else {}
    classname = item["classname"]
    mapped = {name: (position, reader) for name, position, reader in OPTION_FIELDS.get(classname, [])}
    for name, value in settings.items():
        if base.get(name) == value:
            continue
        if name in mapped:
            number = _setting_to_option(value, mapped[name][1])
            if number is not None:
                _write_option(box, mapped[name][0], number)
                continue
        if name == "delay":
            box["delay"] = value
        elif name in ("furni", "antenna"):
            box["items"] = value
        elif name in ("text", "placeholder"):
            box["config"] = value
        elif name == "variable" and classname.startswith("wf_var_"):
            box["config"] = value
            box["variableId"] = _variable_id(str(value), variables, used)
        elif name == "variable" and value:
            ids: list[Any] = box["variableIds"] if isinstance(box.get("variableIds"), list) else []
            box["variableIds"] = [_variable_id(str(value), variables, used), *ids[1:]]
        elif name != "variable" and value != _default(classname, name):
            warnings.append(f"{classname}: the setting {name} cannot go into a G-Presets file yet.")


def export_gpresets(document: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Returns the file and warnings. Anything imported and left alone comes back exactly as it was."""
    saved: dict[str, Any] = document["gpreset"] if isinstance(document.get("gpreset"), dict) else {}
    warnings: list[str] = []
    items = document.get("furni", [])
    extras = copy.deepcopy(saved.get("wired_extras", {}))
    all_boxes = [i["gpreset_box"]["box"] for i in items if isinstance(i.get("gpreset_box"), dict)]
    orphans: list[dict[str, Any]] = saved.get("orphans", [])
    names = _variable_names(extras.get("variables_map"), [*all_boxes, *(o["box"] for o in orphans)])
    variables: dict[str, Any] = (
        extras["variables_map"] if isinstance(extras.get("variables_map"), dict) else {}
    )
    used = [0]
    rows: dict[str, list[tuple[int, Any]]] = {key: [] for key in saved.get("sections", [])}
    next_order = 1_000_000
    for item in items:
        classname = item["classname"]
        section = section_of(classname)
        stored: dict[str, Any] | None = (
            item["gpreset_box"] if isinstance(item.get("gpreset_box"), dict) else None
        )
        if section is None and stored is None:
            continue
        if stored:
            box, base = copy.deepcopy(stored["box"]), friendly_settings(classname, stored["box"], names)
            section, order = stored["section"], stored["order"]
        else:
            box, base = _new_box(classname, warnings), {}
            for name, position, reader in OPTION_FIELDS.get(classname, []):
                number = _setting_to_option(_default(classname, name), reader)
                if number is not None:
                    _write_option(box, position, number)
            order, next_order = next_order, next_order + 1
            if classname.startswith("wf_var_") and "variable" not in (item.get("wired") or {}):
                warnings.append(f"{classname} at {item['x']}, {item['y']} has no variable name.")
        box["wiredId"] = item["id"]
        _apply_settings(item, box, base, variables, used, warnings)
        if not stored and box["items"] and box["furniSources"] == [200]:
            box["furniSources"] = [100]  # Real boxes with picks use 100, and 200 goes with a selector.
        rows.setdefault(str(section), []).append((order, box))
    for orphan in orphans:
        rows.setdefault(orphan["section"], []).append((orphan["order"], copy.deepcopy(orphan["box"])))
    if variables and "variables_map" not in extras:
        extras["variables_map"] = variables
    wired = {key: [box for _, box in sorted(rows[key], key=lambda row: row[0])] for key in rows}
    wired.update(extras)

    out: dict[str, Any] = copy.deepcopy(saved.get("top", {"bindings": []}))
    if saved.get("has_furni", True) or items:
        out["furni"] = [_export_furni(item) for item in items]
    if saved.get("has_wired", True):
        out["wired"] = wired
    if document.get("avatars"):
        warnings.append("Avatars are not part of a G-Presets file, so they were left out.")
    return out, warnings


def shopping_list(
    document: dict[str, Any], details: dict[str, dict[str, Any] | None]
) -> list[dict[str, Any]]:
    counts = Counter(item["classname"] for item in document.get("furni", []))
    rows = []
    for classname, count in sorted(counts.items()):
        info = details.get(classname)
        rows.append(
            {
                "classname": classname,
                "name": info.get("name") if info else classname,
                "count": count,
                "stage": info.get("release_stage") if info else "unknown",
            }
        )
    return rows


def obtainable_warnings(rows: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for row in rows:
        if row["stage"] == "unknown":
            warnings.append(f"{row['classname']} is not in this hotel's catalogue.")
        elif row["stage"] != "live":
            warnings.append(f"{row['classname']} has no catalogue offer, so it may not be obtainable.")
    return warnings


def export_native(name: str, hotel: str, description: str, document: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": NATIVE_FORMAT,
        "version": NATIVE_VERSION,
        "name": name,
        "hotel": hotel,
        "description": description,
        "document": document,
    }


def read_native(file: dict[str, Any]) -> dict[str, Any]:
    version = file.get("version")
    if not isinstance(version, int) or version > NATIVE_VERSION or version < 1:
        raise _invalid("This file came from a newer Wiredbench. Update this one to open it.")
    document = file.get("document")
    if not isinstance(document, dict):
        raise _invalid("This Wiredbench file has no room in it.")
    return document


def detect(file: dict[str, Any]) -> str:
    if file.get("format") == NATIVE_FORMAT:
        return "native"
    if isinstance(file.get("furni"), list) or isinstance(file.get("wired"), dict):
        return "gpresets"
    raise _invalid("This is not a Wiredbench or G-Presets file.")
