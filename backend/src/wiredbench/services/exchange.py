"""Reads and writes room files: Wiredbench's own format, and the G-Presets JSON format.

G-Presets fields are mostly undocumented, so each imported item keeps its original data. Export starts
from that data and changes only what was edited, which means fields this code cannot read survive.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from wiredbench.engine import box_facts
from wiredbench.engine.boxes import BOXES
from wiredbench.engine.operations import OPERATION_CODES
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
# G-Presets will not load a file without these, even when they are empty.
REQUIRED_SECTIONS = ("triggers", "conditions", "effects")
MIN_ROOM = 12
NEW_VARIABLE_ID = 900_000
# Where each setting sits in a box's options list: (setting, position, how the number reads).
# A scale turns the number into seconds, a tuple lists names by number, and bool is 0 or 1.
LONG = (
    "long"  # A 64-bit value in two options: the high word just before the given position, then the low word.
)
VARIABLE_SCOPES = {
    "wf_var_user": "user",
    "wf_var_furni": "furni",
    "wf_var_room": "global",
    "wf_var_context": "context",
}
COMPASS_NUMBERS = dict(enumerate(("y-", "x+y-", "x+", "x+y+", "y+", "x-y+", "x-", "x-y-")))
# Where a box takes its users and furni from. Only the first slot is read and written.
SOURCE_FIELDS = {
    "user_source": ("userSources", "default_user_sources", {0: "trigger", 200: "selector", 201: "signal"}),
    "furni_source": (
        "furniSources",
        "default_furni_sources",
        {0: "trigger", 100: "picks", 200: "selector", 201: "signal"},
    ),
}
AREA_FIELDS = [("area_x", 0, int), ("area_y", 1, int), ("area_width", 2, int), ("area_height", 3, int)]
# A selector's two switches sit on the box itself. The file calls invert "inverse".
SELECTOR_SWITCHES = {"filter": "filter", "invert": "inverse"}
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
    "wf_act_move_rotate": [
        (
            "direction",
            0,
            {
                0: "none",
                1: "random",
                2: "random_x",
                3: "random_y",
                4: "y-",
                5: "x+",
                6: "y+",
                7: "x-",
                8: "x+y-",
                9: "x+y+",
                10: "x-y+",
                11: "x-y-",
            },
        ),
        ("rotation", 1, ("none", "clockwise", "counterclockwise", "random")),
    ],
    "wf_act_rel_mov": [("move_x", 0, int), ("move_y", 1, int)],
    "wf_act_set_altitude": [("altitude", 0, 0.01), ("altitude_change", 1, ("raise", "lower", "set"))],
    "wf_act_move_rotate_user": [
        ("user_move", 0, {-1: "none", **COMPASS_NUMBERS}),
        ("user_turn", 1, {-1: "none", **COMPASS_NUMBERS, 9: "clockwise", 10: "counterclockwise"}),
    ],
    "wf_act_log": [("level", 0, ("0", "1", "2", "3"))],
    "wf_cnd_user_count_in": [("min", 0, int), ("max", 1, int)],
    "wf_cnd_not_user_count": [("min", 0, int), ("max", 1, int)],
    "wf_xtra_execution_limit": [("count", 0, int), ("window_seconds", 1, 0.5)],
    "wf_xtra_random": [("skip", 0, int), ("pick", 1, int)],
    "wf_slc_furni_area": AREA_FIELDS,
    "wf_slc_users_area": AREA_FIELDS,
    "wf_slc_furni_altitude": [("altitude", 0, 0.01), ("altitude_compare", 1, ("less", "equal", "more"))],
    "wf_slc_furni_onfurni": [("stacking", 0, ("above", "below", "level", "tile"))],
    "wf_xtra_filter_users": [("amount", 0, int)],
    "wf_xtra_filter_furni": [("amount", 0, int)],
    "wf_xtra_filter_users_by_var": [("amount", 0, int), ("lowest", 1, bool)],
    "wf_act_toggle_state": [("toggle_type", 0, ("next", "previous"))],
    "wf_act_give_var": [("value", 2, LONG)],
    "wf_act_change_var_val": [
        ("operation", 1, OPERATION_CODES),
        ("value", 4, LONG),
    ],
    "wf_cnd_var_age_match": [
        ("compare", 1, ("less", "equal", "more")),
        ("age_of", 2, ("creation", "update")),
        ("duration", 4, LONG),
        (
            "unit",
            5,
            {
                0: "milliseconds",
                1: "seconds",
                2: "minutes",
                3: "hours",
                4: "days",
                5: "weeks",
                6: "months",
                7: "years",
            },
        ),
    ],
    "wf_cnd_var_val_match": [
        ("compare", 1, {0: "<", 1: "=", 2: ">", 3: "<=", 4: "!=", 5: ">="}),
        ("value", 4, LONG),
    ],
    "wf_xtra_text_output_variable": [
        ("placeholder_type", 0, ("single", "multiple")),
        ("display", 2, ("numeric", "textual")),
    ],
    "wf_var_user": [
        ("availability", 0, {0: "active", 10: "persistent", 11: "shared"}),
        ("has_value", 1, bool),
    ],
    "wf_var_furni": [("has_value", 0, bool), ("availability", 1, {1: "active", 10: "persistent"})],
    "wf_var_room": [("availability", 0, {1: "active", 10: "persistent", 11: "shared"})],
    "wf_var_context": [("has_value", 0, bool)],
}


# Where each box says its value comes from another variable. The next positions after a value are shared:
# position 5 is that variable's target and position 6 says it is read on the same holder.
REFERENCE_FLAG = {"wf_act_give_var": 4, "wf_act_change_var_val": 2, "wf_cnd_var_val_match": 2}
REFERENCE_TARGET, REFERENCE_SAME_HOLDER = 5, 6
TARGET_NUMBERS = {"user": 1, "furni": 0, "global": -10, "context": -20}
# Boxes whose first option says what kind of holder their variable has.
TARGET_FIRST = {
    "wf_act_give_var",
    "wf_act_change_var_val",
    "wf_act_remove_var",
    "wf_cnd_var_val_match",
    "wf_cnd_var_age_match",
    "wf_cnd_has_var",
    "wf_cnd_neg_has_var",
}


def _read_long(options: list[Any], position: int) -> int | None:
    high, low = options[position - 1], options[position]
    if not all(isinstance(word, int) and not isinstance(word, bool) for word in (high, low)):
        return None
    return int((high << 32) | (low & 0xFFFFFFFF))


def _low_word(value: int) -> int:
    low = value & 0xFFFFFFFF
    return low - 2**32 if low >= 2**31 else low


def _write_long(box: dict[str, Any], position: int, value: int) -> None:
    _write_option(box, position, _low_word(value))
    _write_option(box, position - 1, value >> 32)


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
    if reader == LONG:
        return _low_word(int(value)) if isinstance(value, int | float) else None
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
            if position >= len(options):
                continue
            value = (
                _read_long(options, position)
                if reader == LONG
                else _option_to_setting(options[position], reader)
            )
            if value is not None:
                settings[name] = value
    for name, (key, defaults, numbers) in SOURCE_FIELDS.items():
        slots = box.get(key)
        fresh = (box_facts.of(classname) or {}).get(defaults) or [None]
        if (
            name in fields
            and isinstance(slots, list)
            and slots
            and slots[0] != fresh[0]
            and slots[0] in numbers
        ):
            settings[name] = numbers[slots[0]]
    for name, key in SELECTOR_SWITCHES.items():
        if name in fields and isinstance(box.get(key), bool):
            settings[name] = box[key]
    if classname in REFERENCE_FLAG and isinstance(options, list):
        ids = box.get("variableIds")
        flag = REFERENCE_FLAG[classname]
        if flag < len(options) and options[flag] == 1 and isinstance(ids, list) and len(ids) > 1:
            reference = names.get(str(ids[1]))
            if reference:
                settings["from_variable"] = reference
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
    """Starts from a real box's defaults where one has been seen."""
    fact = box_facts.of(classname)
    if fact is None:
        warnings.append(
            f"{classname} has not been seen in a real room, so its options are unknown. Check it after importing."
        )
        fact = {}
    box: dict[str, Any] = {
        "secondItems": [],
        "furniSources": list(fact.get("default_furni_sources", [])),
        "userSources": list(fact.get("default_user_sources", [])),
        "variableIds": ["0"] * fact.get("variable_slots", 0),
        "options": list(fact.get("numbers", [])),
        "config": "",
        "items": [],
    }
    if fact.get("has_delay", classname.startswith("wf_act_")):
        box["delay"] = 0
    if "quantifier" in fact:
        box["quantifier"] = fact["quantifier"]
    if "filter" in fact:
        box["filter"] = fact["filter"]
        box["inverse"] = fact.get("invert", False)
    return box


def _variable_id(name: str, variables: dict[str, Any], used: list[int]) -> str:
    if name not in variables:
        used[0] += 1
        variables[name] = str(NEW_VARIABLE_ID + used[0])
    return str(variables[name])


def _default(classname: str, name: str) -> Any:
    fields = BOXES.get(classname, {}).get("fields", [])
    return next((field["default"] for field in fields if field["name"] == name), None)


def _write_reference(
    box: dict[str, Any],
    classname: str,
    name: str,
    scopes: dict[str, str],
    variables: dict[str, Any],
    used: list[int],
    warnings: list[str],
) -> None:
    """Our simulator always reads the variable on the same holder, so that is what the box is told to do."""
    if name and name not in scopes:
        warnings.append(f"{classname}: a value source must be defined by a variable box in this room.")
        return
    ids: list[Any] = box["variableIds"] if isinstance(box.get("variableIds"), list) else []
    first = ids[0] if ids else "0"
    box["variableIds"] = [first, _variable_id(name, variables, used) if name else "0", *ids[2:]]
    _write_option(box, REFERENCE_FLAG[classname], 1 if name else 0)
    scope = scopes.get(name, "global")
    _write_option(box, REFERENCE_TARGET, TARGET_NUMBERS[scope])
    _write_option(box, REFERENCE_SAME_HOLDER, 1 if scope in ("user", "furni") else 0)


def _apply_settings(
    item: dict[str, Any],
    box: dict[str, Any],
    base: dict[str, Any],
    variables: dict[str, Any],
    used: list[int],
    warnings: list[str],
    scopes: dict[str, str],
) -> None:
    """Writes back only the settings that differ from what the box already said."""
    settings: dict[str, Any] = item["wired"] if isinstance(item.get("wired"), dict) else {}
    classname = item["classname"]
    mapped = {name: (position, reader) for name, position, reader in OPTION_FIELDS.get(classname, [])}
    for name, value in settings.items():
        if base.get(name) == value:
            continue
        if name in mapped and mapped[name][1] == LONG and isinstance(value, int | float):
            _write_long(box, mapped[name][0], int(value))
            continue
        if name in mapped:
            number = _setting_to_option(value, mapped[name][1])
            if number is not None:
                _write_option(box, mapped[name][0], number)
                continue
        if name in SOURCE_FIELDS and value != "default":
            key, _, numbers = SOURCE_FIELDS[name]
            number = next((n for n, label in numbers.items() if label == value), None)
            if number is not None:
                slots = box[key] if isinstance(box.get(key), list) else []
                box[key] = [number, *slots[1:]]
                continue
        if name in SELECTOR_SWITCHES and classname.startswith("wf_slc_"):
            box[SELECTOR_SWITCHES[name]] = bool(value)
        elif name == "from_variable" and classname in REFERENCE_FLAG:
            _write_reference(box, classname, str(value).strip(), scopes, variables, used, warnings)
        elif name == "delay":
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
            scope = scopes.get(str(value).strip())
            if classname in TARGET_FIRST and scope:
                _write_option(box, 0, TARGET_NUMBERS[scope])
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
    scopes = {
        str(i["wired"].get("variable", "")).strip(): VARIABLE_SCOPES[i["classname"]]
        for i in items
        if i["classname"] in VARIABLE_SCOPES and isinstance(i.get("wired"), dict)
    }
    rows: dict[str, list[tuple[int, Any]]] = {key: [] for key in saved.get("sections", REQUIRED_SECTIONS)}
    next_order = 1_000_000
    for item in items:
        classname = item["classname"]
        section = section_of(classname)
        stored: dict[str, Any] | None = (
            item["gpreset_box"] if isinstance(item.get("gpreset_box"), dict) else None
        )
        if section is None and stored is None:
            continue
        # A file can list a box as furni with no settings. Only an edit here makes it more than that.
        if stored is None and "gpreset" in item and not item.get("wired"):
            continue
        if stored:
            box, base = copy.deepcopy(stored["box"]), friendly_settings(classname, stored["box"], names)
            section, order = stored["section"], stored["order"]
        else:
            box, base = _new_box(classname, warnings), {}
            order, next_order = next_order, next_order + 1
            if classname.startswith("wf_var_") and "variable" not in (item.get("wired") or {}):
                warnings.append(f"{classname} at {item['x']}, {item['y']} has no variable name.")
        box["wiredId"] = item["id"]
        _apply_settings(item, box, base, variables, used, warnings, scopes)
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
