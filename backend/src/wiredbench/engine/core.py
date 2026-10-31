"""A deterministic WIRED simulator.

The same room, seed and inputs always give the same result, so runs can be replayed. Time is virtual and
advances only when asked. Room data is untrusted, so bad settings produce a trace line and never an
exception.
"""

from __future__ import annotations

import heapq
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from wiredbench.engine.boxes import BOXES

TICK_MS = 500  # Assumed from delay values in real presets, which are small whole numbers.
EPOCH_SECONDS = 1_700_000_000  # Timestamps look like real ones but are fixed, for replays.
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
MAX_ACTIONS_PER_ADVANCE = 20_000
MAX_ADVANCE_MS = 10 * 60 * 1000
TRACE_LIMIT = 4000
PROBLEMS_KEPT = 20
DASHBOARD_ROWS = 50
DEFAULT_LIMIT = (100, 1)  # Runs per stack per seconds. Assumed: the real default is not public.
MOVES = {"x+": (1, 0), "x-": (-1, 0), "y+": (0, 1), "y-": (0, -1)}
PLACEHOLDER = re.compile(r"\$\(([\w.-]{1,40})\)")


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int) -> int:
    return max(INT64_MIN, min(INT64_MAX, value))


def _ids(value: Any) -> list[int]:
    return (
        [v for v in value if isinstance(v, int) and not isinstance(v, bool)]
        if isinstance(value, list)
        else []
    )


@dataclass
class Holding:
    value: int
    created_ms: int
    updated_ms: int


@dataclass
class Box:
    id: int
    classname: str
    settings: dict[str, Any]
    z: float

    @property
    def spec(self) -> dict[str, Any] | None:
        return BOXES.get(self.classname)

    @property
    def kind(self) -> str:
        return str(self.spec["kind"]) if self.spec else _kind_from_name(self.classname)

    def get(self, name: str, default: Any = None) -> Any:
        if name in self.settings:
            return self.settings[name]
        for spec_field in (self.spec or {}).get("fields", []):
            if spec_field["name"] == name:
                return spec_field["default"]
        return default


def _kind_from_name(classname: str) -> str:
    found = re.search(r"(?:^|_)(trg|act|cnd|slc|xtra|var)(?:_|$)", classname[3:])
    names = {"trg": "trigger", "act": "effect", "cnd": "condition", "slc": "selector", "xtra": "addon"}
    return names.get(found.group(1), "variable") if found else "utility"


@dataclass
class Stack:
    x: int
    y: int
    boxes: list[Box]
    last_runs: deque[int] = field(default_factory=deque)
    unseen: list[int] = field(default_factory=list)
    next_period_ms: dict[int, int] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.x},{self.y}"

    def of(self, kind: str) -> list[Box]:
        return [box for box in self.boxes if box.kind == kind]

    def find(self, classname: str) -> Box | None:
        return next((box for box in self.boxes if box.classname == classname), None)


@dataclass
class Context:
    trigger: Box | None = None
    user: int | None = None
    furni: int | None = None
    signal_users: list[int] = field(default_factory=list)
    signal_furni: list[int] = field(default_factory=list)
    users: list[int] | None = None
    selected_furni: list[int] | None = None
    context_vars: dict[str, Holding] = field(default_factory=dict)


class Engine:
    def __init__(
        self,
        document: dict[str, Any],
        heights: dict[str, float] | None = None,
        seed: int = 1,
        tick_ms: int = TICK_MS,
        furni_states: dict[str, list[int]] | None = None,
    ) -> None:
        self.seed = seed
        self.tick_ms = tick_ms
        self.furni_states = furni_states or {}
        self.random = random.Random(seed)  # noqa: S311 - Replays need a seed; this is not for security.
        self.now_ms = 0
        self.heights = heights or {}
        self.furni: dict[int, dict[str, Any]] = {}
        self.users: dict[int, dict[str, Any]] = {}
        self.boxes_at: dict[tuple[int, int], list[Box]] = defaultdict(list)
        self.variables: dict[str, dict[str, Holding]] = defaultdict(dict)
        self.definitions: dict[str, dict[str, Any]] = {}
        self.queue: list[tuple[int, int, str, dict[str, Any]]] = []
        self.sequence = 0
        self.trace: list[dict[str, Any]] = []
        self.trace_on = True
        self.dropped_trace = 0
        self.timer_start_ms = 0
        self.timer_fired: dict[int, int] = {}
        self.inputs: list[dict[str, Any]] = []
        self.metrics: dict[str, int] = defaultdict(int)
        self.limit_hits = 0
        self.actions_this_advance = 0
        self.messages: list[dict[str, Any]] = []
        self.box_runs: dict[int, int] = defaultdict(int)
        self.stack_work: dict[str, int] = defaultdict(int)
        self.log_counts: dict[str, int] = defaultdict(int)
        self.problems: deque[dict[str, Any]] = deque(maxlen=PROBLEMS_KEPT)
        self._load(document)

    # --- Loading ---

    def _load(self, document: dict[str, Any]) -> None:
        for raw in document.get("furni", []):
            item = {
                "id": raw["id"],
                "classname": raw["classname"],
                "x": raw["x"],
                "y": raw["y"],
                "z": raw.get("z", 0),
                "rot": raw.get("rot", 0),
                "state": raw.get("state", 0),
            }
            self.furni[item["id"]] = item
            if raw["classname"].startswith("wf_"):
                settings = raw.get("wired")
                self.boxes_at[(raw["x"], raw["y"])].append(
                    Box(
                        item["id"],
                        raw["classname"],
                        settings if isinstance(settings, dict) else {},
                        item["z"],
                    )
                )
        self.stacks = [
            Stack(x, y, sorted(boxes, key=lambda box: box.z))
            for (x, y), boxes in sorted(self.boxes_at.items())
        ]
        self.stack_of = {box.id: stack for stack in self.stacks for box in stack.boxes}
        for stack in self.stacks:
            for box in stack.boxes:
                self._define_variable(box)
        for stack in self.stacks:
            for box in stack.of("trigger"):
                if box.classname in ("wf_trg_periodically", "wf_trg_period_short", "wf_trg_period_long"):
                    self._schedule_period(stack, box)
        for raw in document.get("avatars", []):
            self.users[raw["id"]] = {
                "id": raw["id"],
                "name": raw["name"],
                "x": raw["x"],
                "y": raw["y"],
                "dir": raw.get("dir", 2),
            }
        self._log("info", "Room started", seed=self.seed)
        self._fire("wf_trg_room_initializes")

    def _define_variable(self, box: Box) -> None:
        scope = {
            "wf_var_user": "user",
            "wf_var_furni": "furni",
            "wf_var_room": "global",
            "wf_var_context": "context",
        }
        if box.classname in scope and (name := str(box.get("variable", "")).strip()):
            self.definitions[name] = {"scope": scope[box.classname], "time": False}
        elif box.classname == "wf_xtra_var_time_util" and (name := str(box.get("variable", "")).strip()):
            self.definitions.setdefault(name, {"scope": "user", "time": True})["time"] = True

    def _schedule_period(self, stack: Stack, box: Box) -> None:
        seconds = max(0.5, _float(box.get("seconds", 10), 10.0))
        stack.next_period_ms[box.id] = self.now_ms + int(seconds * 1000)

    # --- Trace ---

    def _log(self, kind: str, message: str, **details: Any) -> None:
        self.log_counts[kind] += 1
        if kind in ("error", "limit", "stub"):
            self.problems.append({"at_ms": self.now_ms, "kind": kind, "message": message})
        if not self.trace_on and kind in ("run", "effect", "condition"):
            return
        if len(self.trace) >= TRACE_LIMIT:
            self.trace.pop(0)
            self.dropped_trace += 1
        self.trace.append({"at_ms": self.now_ms, "kind": kind, "message": message, **details})

    def _name(self, classname: str) -> str:
        return classname.removeprefix("wf_")

    # --- Inputs: everything from outside goes through here, so a run can be replayed ---

    def apply_input(self, entry: dict[str, Any]) -> None:
        self.inputs.append({"at_ms": self.now_ms, **entry})
        kind = entry.get("type")
        user = entry.get("user")
        if kind == "move":
            self._move_user(_int(user), _int(entry.get("x")), _int(entry.get("y")))
        elif kind == "say":
            self._say(_int(user), str(entry.get("text", ""))[:500])
        elif kind == "click":
            self._click(_int(user), _int(entry.get("furni")))
        elif kind == "use":
            self._use(_int(user), _int(entry.get("furni")))
        elif kind == "enter":
            self._fire("wf_trg_enter_room", user=_int(user))
        elif kind == "leave":
            self._leave(_int(user))
        elif kind in ("debug_set", "api_set"):
            self._store(str(entry["variable"]), str(entry["key"]), _int(entry["value"]))
            if kind == "api_set":  # Assumed: an API write fires Variable Changed like an effect does.
                holder = str(entry["key"]).partition(":")
                self._changed(str(entry["variable"]), int(holder[2]) if holder[0] == "user" else None)
        elif kind == "api_delete":
            self.variables[str(entry["variable"])].pop(str(entry["key"]), None)
        self._drain()

    def _store(self, name: str, key: str, value: int) -> None:
        holding = self.variables[name].get(key)
        if holding:
            holding.value = value
            holding.updated_ms = self.now_ms
        else:
            self.variables[name][key] = Holding(value, self.now_ms, self.now_ms)

    def _furni_on_tile(self, x: int, y: int) -> list[int]:
        return [i for i, f in self.furni.items() if f["x"] == x and f["y"] == y]

    def _move_user(self, user_id: int, x: int, y: int) -> None:
        user = self.users.get(user_id)
        if not user:
            return
        left = self._furni_on_tile(user["x"], user["y"])
        user["x"], user["y"] = x, y
        for furni in left:
            self._fire("wf_trg_walks_off_furni", user=user_id, furni=furni)
        for furni in self._furni_on_tile(x, y):
            self._fire("wf_trg_walks_on_furni", user=user_id, furni=furni)

    def _say(self, user_id: int, text: str) -> None:
        if user_id not in self.users:
            return
        self._log("info", f"{self.users[user_id]['name']} says: {text}")
        for stack, box in self._triggers("wf_trg_says_something"):
            keyword = str(box.get("text", "")).strip().lower()
            said = text.strip().lower()
            match = "exact" if box.get("exact") is True else str(box.get("match", "contains"))
            if match == "all":
                found = True  # Fires on every message, whatever the box's text says.
            elif match == "exact":
                found = bool(keyword) and said == keyword
            else:
                found = bool(keyword) and keyword in said
            if found:
                self._start(stack, Context(trigger=box, user=user_id))

    def _click(self, user_id: int, furni_id: int) -> None:
        if furni_id in self.furni:
            self._fire("wf_trg_click_furni", user=user_id, furni=furni_id)

    def _use(self, user_id: int, furni_id: int) -> None:
        if furni_id in self.furni:
            self._set_state(furni_id, self._next_state(furni_id))
            self._fire("wf_trg_state_changed", user=user_id, furni=furni_id)

    def _leave(self, user_id: int) -> None:
        if user_id in self.users:
            self._fire("wf_trg_leave_room", user=user_id)
            del self.users[user_id]
            self._log("info", f"User {user_id} left the room")

    # --- Time ---

    def advance(self, ms: int) -> None:
        ms = max(0, min(ms, MAX_ADVANCE_MS))
        end = self.now_ms + ms
        self.actions_this_advance = 0
        while True:
            next_time = self._next_due()
            if next_time is None or next_time > end:
                break
            self.now_ms = max(self.now_ms, next_time)
            self._run_periods()
            self._drain()
            if self.actions_this_advance > MAX_ACTIONS_PER_ADVANCE:
                self._log("limit", "This room did too much work in one step, so the rest was skipped.")
                self.queue.clear()
                break
        self.now_ms = end

    def _next_due(self) -> int | None:
        times = [self.queue[0][0]] if self.queue else []
        times += [t for stack in self.stacks for t in stack.next_period_ms.values()]
        for stack in self.stacks:
            for box in stack.of("trigger"):
                if box.classname == "wf_trg_at_given_time":
                    due = self.timer_start_ms + int(_int(box.get("seconds", 0)) * 1000)
                    if due >= self.now_ms and self.timer_fired.get(box.id) != self.timer_start_ms:
                        times.append(due)
        return min(times) if times else None

    def _run_periods(self) -> None:
        for stack in self.stacks:
            for box in stack.of("trigger"):
                due = stack.next_period_ms.get(box.id)
                if due is not None and due <= self.now_ms:
                    self._schedule_period(stack, box)
                    self._start(stack, Context(trigger=box))
                if (
                    box.classname == "wf_trg_at_given_time"
                    and self.timer_start_ms + _int(box.get("seconds", 0)) * 1000 <= self.now_ms
                    and self.timer_fired.get(box.id) != self.timer_start_ms
                ):
                    self.timer_fired[box.id] = self.timer_start_ms
                    self._start(stack, Context(trigger=box))

    def _push(self, at_ms: int, action: str, payload: dict[str, Any]) -> None:
        self.sequence += 1
        heapq.heappush(self.queue, (at_ms, self.sequence, action, payload))

    def _drain(self) -> None:
        while self.queue and self.queue[0][0] <= self.now_ms:
            _, _, action, payload = heapq.heappop(self.queue)
            self.actions_this_advance += 1
            if self.actions_this_advance > MAX_ACTIONS_PER_ADVANCE:
                self._log("limit", "This room did too much work in one step, so the rest was skipped.")
                self.queue.clear()
                return
            if action == "effect":
                self._run_effect(payload["box"], payload["context"])
            elif action == "signal":
                self._deliver_signal(payload["antennas"], payload["users"], payload["furni"])

    # --- Triggers and stacks ---

    def _triggers(self, classname: str) -> list[tuple[Stack, Box]]:
        return [(stack, box) for stack in self.stacks for box in stack.boxes if box.classname == classname]

    def _fire(self, classname: str, user: int | None = None, furni: int | None = None) -> None:
        for stack, box in self._triggers(classname):
            picks = _ids(box.get("furni", []))
            if (
                furni is not None
                and "furni" in {f["name"] for f in (box.spec or {}).get("fields", [])}
                and furni not in picks
            ):
                continue
            self._start(stack, Context(trigger=box, user=user, furni=furni))

    def _limit_ok(self, stack: Stack) -> bool:
        addon = stack.find("wf_xtra_execution_limit")
        count, default_window = DEFAULT_LIMIT
        window = float(default_window)
        if addon:
            count = max(1, _int(addon.get("count"), 10))
            window = max(0.5, _float(addon.get("window_seconds"), 1.0))
        while stack.last_runs and stack.last_runs[0] <= self.now_ms - window * 1000:
            stack.last_runs.popleft()
        if len(stack.last_runs) >= count:
            self.limit_hits += 1
            self._log(
                "limit", f"Stack at {stack.key} hit its limit of {count} runs per {window} s", stack=stack.key
            )
            return False
        stack.last_runs.append(self.now_ms)
        return True

    def _start(self, stack: Stack, context: Context, ignore_conditions: bool = False) -> None:
        if not self._limit_ok(stack):
            return
        self.metrics[f"stack:{stack.key}"] += 1
        self.stack_work[stack.key] += len(stack.boxes)
        if context.trigger:
            self.box_runs[context.trigger.id] += 1
        label = self._name(context.trigger.classname) if context.trigger else "called"
        self._log("run", f"Stack {stack.key} runs, from {label}", stack=stack.key, user=context.user)
        self._flag_stubs(stack)
        self._apply_selectors(stack, context)
        if not ignore_conditions and not self._conditions_pass(stack, context):
            return
        effects = stack.of("effect")
        chosen = self._choose_effects(stack, effects)
        for box in chosen:
            delay = max(0, min(_int(box.get("delay", 0)), 600)) * self.tick_ms
            self._push(self.now_ms + delay, "effect", {"box": box, "context": context})

    def _flag_stubs(self, stack: Stack) -> None:
        for box in stack.boxes:
            if box.spec is None and box.kind != "utility":
                self._log("stub", f"{self._name(box.classname)} is not simulated yet", box=box.id)

    def _choose_effects(self, stack: Stack, effects: list[Box]) -> list[Box]:
        known = [box for box in effects if box.spec is not None]
        if not known:
            return []
        if stack.find("wf_xtra_random"):
            return [self.random.choice(known)]
        if stack.find("wf_xtra_unseen"):
            if not stack.unseen:
                stack.unseen = [box.id for box in known]
                self.random.shuffle(stack.unseen)
            pick = stack.unseen.pop()
            return [box for box in known if box.id == pick]
        if stack.find("wf_xtra_exec_in_order"):
            # Top of the stack first. Assumed: the direction is not publicly documented.
            return sorted(known, key=lambda box: -box.z)
        # Without Execute In Order the order is not guaranteed, so it varies here and exposes
        # stacks that rely on it by accident.
        shuffled = list(known)
        self.random.shuffle(shuffled)
        return shuffled

    # --- Selectors ---

    def _apply_selectors(self, stack: Stack, ctx: Context) -> None:
        for box in stack.of("selector"):
            self._select(box, ctx)
        for box in stack.of("addon"):
            amount = max(0, _int(box.get("amount", 1), 1))
            if box.classname == "wf_xtra_filter_users" and ctx.users is not None:
                ctx.users = self.random.sample(ctx.users, min(amount, len(ctx.users)))
            elif box.classname == "wf_xtra_filter_furni" and ctx.selected_furni is not None:
                ctx.selected_furni = self.random.sample(
                    ctx.selected_furni, min(amount, len(ctx.selected_furni))
                )
            elif box.classname == "wf_xtra_filter_users_by_var" and ctx.users is not None:
                name = str(box.get("variable", ""))
                ranked = sorted(
                    (u for u in ctx.users if self._holding(name, u) is not None),
                    key=lambda u: self._holding(name, u).value,  # type: ignore[union-attr]
                    reverse=not box.get("lowest"),
                )
                ctx.users = ranked[:amount]

    def _select(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", ""))
        match box.classname:
            case "wf_slc_furni_picks":
                ctx.selected_furni = [i for i in _ids(box.get("furni")) if i in self.furni]
            case "wf_slc_furni_bytype":
                types = {self.furni[i]["classname"] for i in _ids(box.get("furni")) if i in self.furni}
                ctx.selected_furni = [i for i, f in self.furni.items() if f["classname"] in types]
            case "wf_slc_furni_signal":
                ctx.selected_furni = list(ctx.signal_furni)
            case "wf_slc_furni_with_var":
                ctx.selected_furni = [i for i in self.furni if f"furni:{i}" in self.variables[name]]
            case "wf_slc_users_signal":
                ctx.users = list(ctx.signal_users)
            case "wf_slc_users_with_var":
                ctx.users = [u for u in self.users if f"user:{u}" in self.variables[name]]
            case "wf_slc_users_onfurni":
                tiles = {
                    (self.furni[i]["x"], self.furni[i]["y"])
                    for i in _ids(box.get("furni"))
                    if i in self.furni
                }
                ctx.users = [u for u, d in self.users.items() if (d["x"], d["y"]) in tiles]
            case "wf_slc_users_byname":
                wanted = {n.strip().lower() for n in str(box.get("names", "")).splitlines() if n.strip()}
                ctx.users = [u for u, d in self.users.items() if d["name"].lower() in wanted]

    def _users_for(self, box: Box, ctx: Context) -> list[int]:
        source = box.get("user_source", "default")
        if source == "trigger":
            return [ctx.user] if ctx.user is not None else []
        if source == "signal":
            return list(ctx.signal_users)
        if source == "selector":
            return list(ctx.users or [])
        if ctx.users is not None:
            return list(ctx.users)
        if ctx.user is not None:
            return [ctx.user]
        return list(ctx.signal_users)

    def _furni_for(self, box: Box, ctx: Context) -> list[int]:
        source = box.get("furni_source", "default")
        picks = [i for i in _ids(box.get("furni")) if i in self.furni]
        if source == "picks":
            return picks
        if source == "trigger":
            return [ctx.furni] if ctx.furni is not None else []
        if source == "signal":
            return list(ctx.signal_furni)
        if source == "selector":
            return list(ctx.selected_furni or [])
        return ctx.selected_furni if ctx.selected_furni is not None else picks

    # --- Conditions ---

    def _conditions_pass(self, stack: Stack, ctx: Context) -> bool:
        conditions = stack.of("condition")
        known = [box for box in conditions if box.spec is not None]
        if not known:
            return True
        results = [self._check(box, ctx) for box in known]
        for box, result in zip(known, results, strict=True):
            self._log(
                "condition", f"{self._name(box.classname)}: {'passed' if result else 'failed'}", box=box.id
            )
        return any(results) if stack.find("wf_xtra_or_eval") else all(results)

    def _on_furni(self, user_id: int, picks: list[int]) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        return any(
            (self.furni[i]["x"], self.furni[i]["y"]) == (user["x"], user["y"])
            for i in picks
            if i in self.furni
        )

    def _check(self, box: Box, ctx: Context) -> bool:
        users = self._users_for(box, ctx)
        picks = _ids(box.get("furni", []))
        name = str(box.get("variable", ""))
        match box.classname:
            case "wf_cnd_has_var":
                return bool(users) and all(self._holding(name, u, ctx) is not None for u in users)
            case "wf_cnd_neg_has_var":
                return all(self._holding(name, u, ctx) is None for u in users)
            case "wf_cnd_var_val_match":
                return bool(users) and all(self._compare(box, self._holding(name, u, ctx)) for u in users)
            case "wf_cnd_trggrer_on_frn":
                return bool(users) and all(self._on_furni(u, picks) for u in users)
            case "wf_cnd_not_trggrer_on":
                return all(not self._on_furni(u, picks) for u in users)
            case "wf_cnd_furnis_hv_avtrs":
                return bool(picks) and all(self._has_users(i) for i in picks)
            case "wf_cnd_not_hv_avtrs":
                return all(not self._has_users(i) for i in picks)
            case "wf_cnd_has_furni_on":
                return any(self._has_furni_on(i) for i in picks)
            case "wf_cnd_not_furni_on":
                return all(not self._has_furni_on(i) for i in picks)
            case "wf_cnd_stuff_is":
                return ctx.furni in picks
            case "wf_cnd_not_stuff_is":
                return ctx.furni not in picks
            case "wf_cnd_user_count_in":
                return _int(box.get("min", 0)) <= len(self.users) <= _int(box.get("max", 50), 50)
            case "wf_cnd_not_user_count":
                return not _int(box.get("min", 0)) <= len(self.users) <= _int(box.get("max", 50), 50)
            case "wf_cnd_triggerer_match":
                return self._user_name(ctx.user).lower() == str(box.get("name", "")).lower()
            case "wf_cnd_not_triggerer_match":
                return self._user_name(ctx.user).lower() != str(box.get("name", "")).lower()
            case "wf_cnd_time_less_than":
                return self.now_ms - self.timer_start_ms < _int(box.get("seconds", 0)) * 1000
            case "wf_cnd_time_more_than":
                return self.now_ms - self.timer_start_ms > _int(box.get("seconds", 0)) * 1000
        return True

    def _compare(self, box: Box, holding: Holding | None) -> bool:
        if holding is None:
            return False
        target = _int(box.get("value", 0))
        match box.get("compare", "="):
            case "=":
                return holding.value == target
            case "!=":
                return holding.value != target
            case ">":
                return holding.value > target
            case ">=":
                return holding.value >= target
            case "<":
                return holding.value < target
            case "<=":
                return holding.value <= target
        return False

    def _has_users(self, furni_id: int) -> bool:
        item = self.furni.get(furni_id)
        if not item:
            return False
        return any((u["x"], u["y"]) == (item["x"], item["y"]) for u in self.users.values())

    def _has_furni_on(self, furni_id: int) -> bool:
        item = self.furni.get(furni_id)
        if not item:
            return False
        return any(
            f["x"] == item["x"] and f["y"] == item["y"] and f["z"] > item["z"] and i != furni_id
            for i, f in self.furni.items()
        )

    def _user_name(self, user_id: int | None) -> str:
        user = self.users.get(user_id) if user_id is not None else None
        return user["name"] if user else ""

    # --- Variables ---

    def _key(self, name: str, user: int | None) -> str:
        scope = self.definitions.get(name, {}).get("scope", "user")
        return "global" if scope == "global" else f"{scope}:{user}"

    def _holding(self, name: str, user: int | None, ctx: Context | None = None) -> Holding | None:
        if self.definitions.get(name, {}).get("scope") == "context":
            return ctx.context_vars.get(name) if ctx else None
        return self.variables[name].get(self._key(name, user))

    def _write(self, name: str, user: int | None, holding: Holding, ctx: Context | None) -> None:
        if self.definitions.get(name, {}).get("scope") == "context" and ctx is not None:
            ctx.context_vars[name] = holding
            return
        self.variables[name][self._key(name, user)] = holding

    def _changed(self, name: str, user: int | None) -> None:
        for stack, box in self._triggers("wf_trg_var_changed"):
            if box.get("variable") == name:
                self._start(stack, Context(trigger=box, user=user))

    def _read(self, holding: Holding, field_name: str) -> int:
        if field_name == "creation":
            return EPOCH_SECONDS + holding.created_ms // 1000
        if field_name == "update":
            return EPOCH_SECONDS + holding.updated_ms // 1000
        return holding.value

    # --- Effects ---

    def _run_effect(self, box: Box, ctx: Context) -> None:
        self.metrics[f"box:{box.classname}"] += 1
        self.box_runs[box.id] += 1
        handler = getattr(self, f"_do_{box.classname.removeprefix('wf_act_')}", None)
        if handler is None:
            self._log("stub", f"{self._name(box.classname)} is not simulated yet", box=box.id)
            return
        self._log("effect", self._name(box.classname), box=box.id)
        handler(box, ctx)

    def _do_give_var(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        if not name:
            self._log("error", "Give Variable has no variable chosen", box=box.id)
            return
        for user in self._users_for(box, ctx):
            if self._holding(name, user, ctx) is not None and not box.get("overwrite"):
                continue
            self._write(name, user, Holding(_clamp(_int(box.get("value", 0))), self.now_ms, self.now_ms), ctx)
            self._changed(name, user)

    def _do_remove_var(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        for user in self._users_for(box, ctx):
            if self.definitions.get(name, {}).get("scope") == "context":
                ctx.context_vars.pop(name, None)
            else:
                self.variables[name].pop(self._key(name, user), None)
            self._changed(name, user)

    def _do_change_var_val(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        reference = str(box.get("from_variable", "")).strip()
        for user in self._users_for(box, ctx):
            holding = self._holding(name, user, ctx)
            if holding is None:
                self._log("error", f"{name} is not set for user {user}, so it was not changed", box=box.id)
                continue
            amount = _int(box.get("value", 0))
            if reference:
                source = self._holding(reference, user, ctx)
                if source is None:
                    self._log("error", f"{reference} is not set for user {user}", box=box.id)
                    continue
                amount = self._read(source, str(box.get("from_field", "value")))
            operation = box.get("operation", "set")
            value = holding.value
            if operation == "set":
                value = amount
            elif operation == "add":
                value += amount
            elif operation == "subtract":
                value -= amount
            elif operation == "multiply":
                value *= amount
            elif operation == "divide":
                value = int(value / amount) if amount else value
            holding.value = _clamp(value)
            holding.updated_ms = self.now_ms
            self._changed(name, user)

    def _send(self, box: Box, ctx: Context) -> None:
        antennas = _ids(box.get("antenna", []))
        users = self._users_for(box, ctx)
        furni = self._furni_for(box, ctx) if "furni" in box.settings else []
        # One signal per user. Assumed, because the article's per-user conditions need it.
        targets: list[int | None] = list(users) or [None]
        for user in targets:
            self._push(
                self.now_ms,
                "signal",
                {"antennas": antennas, "users": [user] if user is not None else [], "furni": furni},
            )

    _do_send_signal = _send
    _do_neg_send_signal = _send

    def _deliver_signal(self, antennas: list[int], users: list[int], furni: list[int]) -> None:
        self.metrics["signals"] += 1
        self._log("signal", f"Signal to antennas {antennas}", users=users)
        for stack, box in self._triggers("wf_trg_recv_signal"):
            if set(_ids(box.get("antenna", []))) & set(antennas):
                self._start(stack, Context(trigger=box, signal_users=list(users), signal_furni=list(furni)))

    def _call(self, box: Box, ctx: Context) -> None:
        for furni_id in _ids(box.get("furni", [])):
            stack = self.stack_of.get(furni_id)
            if stack:
                # Execute Wired Stacks runs them regardless of their triggers and conditions.
                self._start(
                    stack, Context(trigger=box, user=ctx.user, furni=ctx.furni), ignore_conditions=True
                )

    _do_call_stacks = _call
    _do_neg_call_stacks = _call

    def _states(self, furni_id: int) -> list[int]:
        # Without art to read, assume an on and off furni.
        return self.furni_states.get(self.furni[furni_id]["classname"]) or [0, 1]

    def _next_state(self, furni_id: int) -> int:
        states = self._states(furni_id)
        current = self.furni[furni_id]["state"]
        return states[(states.index(current) + 1) % len(states)] if current in states else states[0]

    def _set_state(self, furni_id: int, state: int) -> None:
        item = self.furni.get(furni_id)
        if item:
            item["state"] = state
            self._fire("wf_trg_stuff_state", furni=furni_id)

    def _do_toggle_state(self, box: Box, ctx: Context) -> None:
        for furni_id in self._furni_for(box, ctx):
            self._set_state(furni_id, self._next_state(furni_id))

    def _do_toggle_to_rnd(self, box: Box, ctx: Context) -> None:
        for furni_id in self._furni_for(box, ctx):
            self._set_state(furni_id, self.random.choice(self._states(furni_id)))

    def _text(self, box: Box, ctx: Context, user: int | None) -> str:
        values: dict[str, str] = {}
        stack = self.stack_of.get(box.id)
        for addon in stack.of("addon") if stack else []:
            if addon.classname == "wf_xtra_text_output_username":
                values[str(addon.get("placeholder", "user"))] = self._user_name(user)
            elif addon.classname == "wf_xtra_text_output_variable":
                name = str(addon.get("variable", ""))
                holding = self._holding(name, user, ctx)
                values[str(addon.get("placeholder", name))] = self._connected(stack, name, holding)
        return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), str(box.get("text", "")))

    def _connected(self, stack: Stack | None, name: str, holding: Holding | None) -> str:
        if holding is None:
            return ""
        for addon in stack.of("addon") if stack else []:
            if addon.classname == "wf_xtra_var_text_connector" and addon.get("variable") == name:
                for line in str(addon.get("mapping", "")).splitlines():
                    key, _, text = line.partition("=")
                    if key.strip() == str(holding.value):
                        return text.strip()
        return str(holding.value)

    def _do_show_message(self, box: Box, ctx: Context) -> None:
        for user in self._users_for(box, ctx):
            text = self._text(box, ctx, user)
            self.messages.append({"at_ms": self.now_ms, "user": user, "text": text})
            self._log("message", f"To {self._user_name(user)}: {text}")

    def _do_log(self, box: Box, ctx: Context) -> None:
        self._log("log", self._text(box, ctx, ctx.user))

    _do_neg_log = _do_log

    def _do_reset_timers(self, _box: Box, _ctx: Context) -> None:
        self.timer_start_ms = self.now_ms

    def _teleport(self, box: Box, ctx: Context) -> None:
        picks = [i for i in _ids(box.get("furni")) if i in self.furni]
        if not picks:
            return
        for user in self._users_for(box, ctx):
            target = self.furni[self.random.choice(picks)]
            if user in self.users:
                self._move_user(user, target["x"], target["y"])

    _do_teleport_to = _teleport
    _do_user_to_furni = _teleport

    def _do_move_rotate(self, box: Box, ctx: Context) -> None:
        for furni_id in self._furni_for(box, ctx):
            item = self.furni[furni_id]
            dx, dy = MOVES.get(str(box.get("direction", "none")), (0, 0))
            item["x"] += dx
            item["y"] += dy
            rotation = str(box.get("rotation", "none"))
            turn = {"clockwise": 2, "counterclockwise": -2}.get(rotation, 0)
            if rotation == "random":
                turn = self.random.choice((0, 2, 4, 6))
            item["rot"] = (item["rot"] + turn) % 8

    # --- Inspection ---

    def view_variables(self) -> list[dict[str, Any]]:
        rows = []
        for name in sorted(self.definitions | dict.fromkeys(self.variables, {})):
            for key, holding in sorted(self.variables[name].items()):
                rows.append(
                    {
                        "variable": name,
                        "holder": key,
                        "value": str(holding.value),
                        "created_ms": holding.created_ms,
                        "updated_ms": holding.updated_ms,
                    }
                )
        return rows

    def dashboard(self) -> dict[str, Any]:
        """Counts for the dashboard. Work is boxes visited, so it is simulated cost and not hotel time."""
        boxes: list[dict[str, Any]] = [
            {
                "id": furni_id,
                "classname": self.furni[furni_id]["classname"],
                "x": self.furni[furni_id]["x"],
                "y": self.furni[furni_id]["y"],
                "runs": runs,
            }
            for furni_id, runs in self.box_runs.items()
            if furni_id in self.furni
        ]
        stacks: list[dict[str, Any]] = [
            {"stack": stack.key, "runs": self.metrics[f"stack:{stack.key}"], "work": work}
            for stack in self.stacks
            if (work := self.stack_work.get(stack.key, 0))
        ]
        return {
            "now_ms": self.now_ms,
            "boxes": sorted(boxes, key=lambda b: (-b["runs"], b["id"]))[:DASHBOARD_ROWS],
            "stacks": sorted(stacks, key=lambda s: (-s["work"], s["stack"]))[:DASHBOARD_ROWS],
            "signals": self.metrics["signals"],
            "errors": self.log_counts["error"],
            "stubs": self.log_counts["stub"],
            "limit_hits": self.limit_hits,
            "problems": list(reversed(self.problems)),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "now_ms": self.now_ms,
            "furni": sorted(
                ({k: f[k] for k in ("id", "x", "y", "z", "rot", "state")} for f in self.furni.values()),
                key=lambda f: f["id"],
            ),
            "users": sorted(self.users.values(), key=lambda u: u["id"]),
            "variables": self.view_variables(),
            "limit_hits": self.limit_hits,
            "metrics": dict(sorted(self.metrics.items())),
        }


def replay(
    document: dict[str, Any],
    seed: int,
    inputs: list[dict[str, Any]],
    until_ms: int,
    heights: dict[str, float] | None = None,
    tick_ms: int = TICK_MS,
    furni_states: dict[str, list[int]] | None = None,
) -> Engine:
    """Rebuilds a run from its inputs. The result matches the original run exactly."""
    engine = Engine(document, heights, seed, tick_ms, furni_states)
    for entry in inputs:
        when = entry["at_ms"]
        if when > engine.now_ms:
            engine.advance(when - engine.now_ms)
        engine.apply_input({k: v for k, v in entry.items() if k != "at_ms"})
    if until_ms > engine.now_ms:
        engine.advance(until_ms - engine.now_ms)
    return engine
