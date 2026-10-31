"""Running rooms, and the debug command grammar. Commands are parsed by fixed rules and never run as code."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from wiredbench.engine.core import INT64_MAX, INT64_MIN, TICK_MS, Engine, Holding

MAX_RUNNING = 8
NAME = r"[\w.-]{1,64}"
COMMANDS: list[tuple[str, re.Pattern[str]]] = [
    ("vars_user", re.compile(rf":vars user ({NAME})")),
    ("vars_furni", re.compile(r":vars furni (\d{1,9})")),
    ("vars_global", re.compile(r":vars global")),
    ("set", re.compile(rf":set (user|furni|global) ({NAME}) ({NAME}) (-?\d{{1,19}})")),
    ("trace", re.compile(r":trace (on|off)")),
    ("pause", re.compile(r":pause")),
    ("resume", re.compile(r":resume")),
    ("step", re.compile(r":step")),
    ("as", re.compile(rf":as ({NAME})")),
]
HELP = (
    "Commands: :vars user <name>, :vars furni <id>, :vars global, :set <user|furni|global> <target> <name> <value>, "
    ":trace on|off, :pause, :resume, :step, :as <name>"
)


@dataclass
class Run:
    engine: Engine
    lock: threading.Lock
    paused: bool = False
    acting_as: int | None = None


class RunRegistry:
    def __init__(self) -> None:
        self._runs: OrderedDict[int, Run] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, sandbox_id: int, document: dict[str, Any], seed: int) -> Run:
        run = Run(Engine(document, seed=seed), threading.Lock())
        with self._lock:
            self._runs[sandbox_id] = run
            self._runs.move_to_end(sandbox_id)
            while len(self._runs) > MAX_RUNNING:
                self._runs.popitem(last=False)
        return run

    def get(self, sandbox_id: int) -> Run | None:
        with self._lock:
            run = self._runs.get(sandbox_id)
            if run:
                self._runs.move_to_end(sandbox_id)
            return run

    def stop(self, sandbox_id: int) -> None:
        with self._lock:
            self._runs.pop(sandbox_id, None)


def _user_id(engine: Engine, name: str) -> int | None:
    return next((u["id"] for u in engine.users.values() if u["name"].lower() == name.lower()), None)


def _rows(engine: Engine, holder: str) -> list[str]:
    return [f"{r['variable']} = {r['value']}" for r in engine.view_variables() if r["holder"] == holder]


def run_command(run: Run, text: str) -> str:
    """Returns the answer to show. Anything outside the grammar only gets the help text."""
    engine = run.engine
    command = text.strip()
    for name, pattern in COMMANDS:
        if match := pattern.fullmatch(command):
            return _execute(run, engine, name, match.groups())
    return HELP


def _execute(run: Run, engine: Engine, name: str, args: tuple[str, ...]) -> str:
    match name:
        case "vars_user":
            user = _user_id(engine, args[0])
            if user is None:
                return f"No user called {args[0]}."
            return "\n".join(_rows(engine, f"user:{user}")) or f"{args[0]} has no variables."
        case "vars_furni":
            return "\n".join(_rows(engine, f"furni:{args[0]}")) or f"Furni {args[0]} has no variables."
        case "vars_global":
            return "\n".join(_rows(engine, "global")) or "No global variables are set."
        case "set":
            return _set(engine, *args)
        case "trace":
            engine.trace_on = args[0] == "on"
            return f"Trace is {args[0]}."
        case "pause":
            run.paused = True
            return "Paused."
        case "resume":
            run.paused = False
            return "Running."
        case "step":
            run.paused = True
            engine.advance(TICK_MS)
            return f"Stepped to {engine.now_ms / 1000:.1f} s."
        case "as":
            user = _user_id(engine, args[0])
            if user is None:
                return f"No user called {args[0]}."
            run.acting_as = user
            return f"Acting as {args[0]}."
    return HELP


def _set(engine: Engine, scope: str, target: str, name: str, raw: str) -> str:
    value = int(raw)
    if not INT64_MIN <= value <= INT64_MAX:
        return "That value is out of range."
    if scope == "user":
        user = _user_id(engine, target)
        if user is None:
            return f"No user called {target}."
        key = f"user:{user}"
    elif scope == "furni":
        if not target.isdigit() or int(target) not in engine.furni:
            return f"No furni with ID {target}."
        key = f"furni:{target}"
    else:
        key = "global"
    holding = engine.variables[name].get(key)
    if holding:
        holding.value = value
        holding.updated_ms = engine.now_ms
    else:
        engine.variables[name][key] = Holding(value, engine.now_ms, engine.now_ms)
    engine.inputs.append(
        {"at_ms": engine.now_ms, "type": "debug_set", "variable": name, "key": key, "value": value}
    )
    return f"{name} = {value}"


def state(run: Run, since: int) -> dict[str, Any]:
    engine = run.engine
    start = max(0, since - engine.dropped_trace)
    return {
        **engine.snapshot(),
        "paused": run.paused,
        "acting_as": run.acting_as,
        "seed": engine.seed,
        "trace": engine.trace[start:],
        "trace_next": engine.dropped_trace + len(engine.trace),
        "messages": engine.messages[-20:],
    }
