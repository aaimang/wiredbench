"""Finds stacks that cannot work as built, without running them.

Errors stop a box working here. Warnings are usually mistakes, but can be deliberate. Imported boxes keep settings
this project cannot read yet, so an empty setting on one proves nothing and only broken references are reported.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from wiredbench.engine.boxes import BOXES
from wiredbench.engine.core import Box

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}
CALLERS = {"wf_act_call_stacks", "wf_act_neg_call_stacks"}
SENDERS = {"wf_act_send_signal", "wf_act_neg_send_signal"}
RECEIVER = "wf_trg_recv_signal"
DEFINERS = {"wf_var_user", "wf_var_furni", "wf_var_room", "wf_var_context"}


def _ids(value: Any) -> list[int]:
    return [item for item in value if isinstance(item, int)] if isinstance(value, list) else []


class _Room:
    def __init__(self, document: dict[str, Any]) -> None:
        self.issues: list[dict[str, Any]] = []
        self.items = [item for item in document.get("furni", []) if isinstance(item, dict)]
        self.ids = {item.get("id") for item in self.items}
        self.imported = {item["id"] for item in self.items if "gpreset_box" in item}
        self.stacks: dict[tuple[int, int], list[Box]] = defaultdict(list)
        for item in self.items:
            if str(item.get("classname", "")).startswith("wf_"):
                settings: dict[str, Any] = item["wired"] if isinstance(item.get("wired"), dict) else {}
                box = Box(item["id"], item["classname"], settings, item.get("z", 0))
                self.stacks[(item["x"], item["y"])].append(box)
        self.where = {box.id: tile for tile, boxes in self.stacks.items() for box in boxes}
        saved: dict[str, Any] = document["gpreset"] if isinstance(document.get("gpreset"), dict) else {}
        extras: dict[str, Any] = saved["wired_extras"] if isinstance(saved.get("wired_extras"), dict) else {}
        mapped = extras.get("variables_map")
        self.defined = set(mapped) if isinstance(mapped, dict) else set()

    def add(self, severity: str, code: str, box: Box, message: str) -> None:
        x, y = self.where[box.id]
        self.issues.append(
            {
                "severity": severity,
                "code": code,
                "box": box.id,
                "classname": box.classname,
                "x": x,
                "y": y,
                "message": message,
            }
        )

    def boxes(self) -> list[Box]:
        return [box for boxes in self.stacks.values() for box in boxes]

    def fields(self, box: Box) -> set[str]:
        return {field["name"] for field in (box.spec or {}).get("fields", [])}


def _check_references(room: _Room) -> None:
    for box in room.boxes():
        for name in ("furni", "antenna"):
            for furni_id in _ids(box.settings.get(name)):
                if furni_id not in room.ids:
                    room.add(
                        ERROR, "missing_furni", box, f"It picks furni {furni_id}, which is not in the room."
                    )


def _check_required(room: _Room) -> None:
    for box in room.boxes():
        if box.id in room.imported:
            continue
        fields = room.fields(box)
        uses_picks = "furni_source" not in fields or box.get("furni_source") == "picks"
        if "furni" in fields and uses_picks and not _ids(box.get("furni")):
            room.add(ERROR, "no_picks", box, "It has no furni picked.")
        if "antenna" in fields and not _ids(box.get("antenna")):
            room.add(ERROR, "no_antenna", box, "It has no antenna picked.")
        if "variable" in fields and not str(box.get("variable", "")).strip():
            room.add(ERROR, "no_variable", box, "It has no variable chosen.")
        says = box.classname == "wf_trg_says_something" and box.get("match") != "all"
        if says and not str(box.get("text", "")).strip():
            room.add(ERROR, "no_keyword", box, "It has no keyword, so it never runs.")


def _check_stack_shape(room: _Room) -> None:
    called: set[tuple[int, int]] = set()
    for box in room.boxes():
        if box.classname in CALLERS:
            called |= {
                room.where[furni_id] for furni_id in _ids(box.settings.get("furni")) if furni_id in room.where
            }
    for tile, boxes in room.stacks.items():
        kinds = {box.kind for box in boxes}
        working = [box for box in boxes if box.kind in ("effect", "condition", "selector")]
        if "trigger" not in kinds and working and tile not in called:
            room.add(
                WARNING, "no_trigger", working[0], "Nothing starts this stack, because it has no trigger."
            )
        if "trigger" in kinds and "effect" not in kinds:
            trigger = next(box for box in boxes if box.kind == "trigger")
            room.add(WARNING, "no_effect", trigger, "This stack does nothing, because it has no effect.")
        for box in boxes:
            source = box.settings.get("user_source"), box.settings.get("furni_source")
            if "selector" in source and "selector" not in kinds:
                room.add(
                    WARNING, "no_selector", box, "It uses selected targets, but its stack has no selector."
                )
            if "signal" in source and RECEIVER not in {other.classname for other in boxes}:
                room.add(
                    WARNING, "no_signal", box, "It uses a signal's targets, but its stack receives no signal."
                )


def _check_signals(room: _Room) -> None:
    sent: set[int] = set()
    received: set[int] = set()
    for box in room.boxes():
        if box.classname in SENDERS:
            sent |= set(_ids(box.settings.get("antenna")))
        elif box.classname == RECEIVER:
            received |= set(_ids(box.settings.get("antenna")))
    for box in room.boxes():
        antennas = set(_ids(box.settings.get("antenna")))
        if box.classname in SENDERS and antennas and not antennas & received:
            room.add(WARNING, "no_receiver", box, "No stack receives this signal.")
        elif box.classname == RECEIVER and antennas and not antennas & sent:
            room.add(WARNING, "no_sender", box, "No effect in this room sends this signal.")


def _check_variables(room: _Room) -> None:
    scopes: dict[str, set[str]] = defaultdict(set)
    for box in room.boxes():
        name = str(box.settings.get("variable", "")).strip()
        if box.classname in DEFINERS and name:
            scopes[name].add(box.classname)
    for box in room.boxes():
        name = str(box.settings.get("variable", "")).strip()
        if box.classname in DEFINERS and len(scopes[name]) > 1:
            room.add(ERROR, "variable_clash", box, f"{name} is defined with different types.")
    known = set(scopes) | room.defined
    for box in room.boxes():
        if box.classname in DEFINERS:
            continue
        for setting in ("variable", "from_variable"):
            name = str(box.settings.get(setting, "")).strip()
            # Names starting with @ are the room's own internal variables.
            if name and not name.startswith("@") and name not in known:
                room.add(ERROR, "undefined_variable", box, f"{name} is not defined by any variable box here.")


def _check_simulation(room: _Room) -> None:
    seen: set[str] = set()
    for box in room.boxes():
        if box.classname not in BOXES and box.kind != "utility" and box.classname not in seen:
            seen.add(box.classname)
            room.add(
                INFO, "not_simulated", box, "This box is not simulated yet, so a run skips what it does."
            )


def check_room(document: dict[str, Any]) -> list[dict[str, Any]]:
    room = _Room(document)
    for check in (_check_references, _check_required, _check_stack_shape, _check_signals, _check_variables):
        check(room)
    _check_simulation(room)
    return sorted(
        room.issues, key=lambda i: (SEVERITY_ORDER[i["severity"]], i["x"], i["y"], i["box"], i["code"])
    )
