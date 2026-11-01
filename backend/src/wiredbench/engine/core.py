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

from wiredbench.engine import operations
from wiredbench.engine.boxes import BOXES, TIME_UNITS

TICK_MS = 500  # Assumed from delay values in real presets, which are small whole numbers.
MAX_DELAY_MS = 60_000  # The largest millisecond delay seen in a real room.
EPOCH_SECONDS = 1_700_000_000  # Timestamps look like real ones but are fixed, for replays.
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
MAX_ACTIONS_PER_ADVANCE = 20_000
MAX_ADVANCE_MS = 10 * 60 * 1000
TRACE_LIMIT = 4000
PROBLEMS_KEPT = 20
DASHBOARD_ROWS = 50
DEFAULT_LIMIT = (100, 1)  # Runs per stack per seconds. Assumed: the real default is not public.
MOVES = {
    "y-": (0, -1),
    "x+y-": (1, -1),
    "x+": (1, 0),
    "x+y+": (1, 1),
    "y+": (0, 1),
    "x-y+": (-1, 1),
    "x-": (-1, 0),
    "x-y-": (-1, -1),
}
MAX_ALTITUDE = 8000
TEAMS = ("red", "green", "blue", "yellow")
MAX_POINTS = 1000
MAX_TIMES = 10
# A real room leaves these as they are when Toggle Furni State points at them.
NOT_WIRED_TOGGLED = {"wf_floor_switch1", "wf_floor_switch2"}
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


def _hundredths(value: Any) -> int:
    """Heights compare in hundredths of a tile, which is as fine as a box can state them."""
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError, OverflowError):
        return 0


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
        self.game_running = False
        self.team_scores = dict.fromkeys(TEAMS, 0)
        self.score_grants: dict[tuple[int, int | None], int] = defaultdict(int)
        self.problems: deque[dict[str, Any]] = deque(maxlen=PROBLEMS_KEPT)
        self._load(document)

    # --- Loading ---

    def _load(self, document: dict[str, Any]) -> None:
        room = document.get("room")
        self.room_size = (
            (_int(room.get("width")), _int(room.get("height")))
            if isinstance(room, dict) and "width" in room and "height" in room
            else None
        )
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
                "team": None,
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
            if box.classname == "wf_var_room":
                # Live: a global nothing has set already reads 0, in the box and from the API.
                self.variables[name]["global"] = Holding(0, self.now_ms, self.now_ms)
        elif box.classname == "wf_xtra_var_time_util" and (name := str(box.get("variable", "")).strip()):
            self.definitions.setdefault(name, {"scope": "user", "time": True})["time"] = True

    def _schedule_period(self, stack: Stack, box: Box) -> None:
        shortest = 0.05 if box.classname == "wf_trg_period_short" else 0.5
        seconds = max(shortest, _float(box.get("seconds", 10), 10.0))
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
        elif kind == "game_start":
            self._game_start()
        elif kind == "game_end":
            self._game_end()
        elif kind == "turn":
            if (who := self.users.get(_int(user))) is not None:
                who["dir"] = _int(entry.get("dir")) % 8
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
                self._changed(
                    str(entry["variable"]), int(holder[2]) if holder[0] in ("user", "furni") else None
                )
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

    def _game_start(self) -> None:
        self.team_scores = dict.fromkeys(TEAMS, 0)
        self.score_grants.clear()
        self.game_running = True
        self._log("info", "Game started")
        self._fire("wf_trg_game_starts")

    def _game_end(self) -> None:
        if self.game_running:
            self.game_running = False
            self._log("info", "Game ended")
            self._fire("wf_trg_game_ends")

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
            self._push(self.now_ms + self._delay_ms(box), "effect", {"box": box, "context": context})

    def _delay_ms(self, box: Box) -> int:
        """Positive delays are the box's standard mode, in half seconds. Negative ones are precise, in milliseconds."""
        delay = _int(box.get("delay", 0))
        return min(-delay, MAX_DELAY_MS) if delay < 0 else min(delay, 600) * self.tick_ms

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
        selectors = stack.of("selector")
        # Picks add up first. Filters then narrow them, wherever they stand in the pile.
        for box in [b for b in selectors if not b.get("filter")] + [b for b in selectors if b.get("filter")]:
            self._select(box, ctx)
        if ctx.selected_furni is not None:
            ctx.selected_furni.sort()
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
        if box.spec is None:
            return
        users = box.classname.startswith("wf_slc_users")
        room: list[int] = list(self.users if users else self.furni)
        found = self._matches(box, ctx)
        if box.get("invert"):
            found = [i for i in room if i not in found]
        current = (ctx.users if users else ctx.selected_furni) or []
        if box.get("filter"):
            result = [i for i in current if i in found]
        else:
            result = [*current, *(i for i in found if i not in current)]
        if users:
            ctx.users = result
        else:
            ctx.selected_furni = result

    def _in_area(self, box: Box, x: int, y: int) -> bool:
        left, top = _int(box.get("area_x")), _int(box.get("area_y"))
        return left <= x < left + _int(box.get("area_width")) and top <= y < top + _int(
            box.get("area_height")
        )

    def _at_altitude(self, box: Box, z: float) -> bool:
        wanted, height = _hundredths(box.get("altitude")), _hundredths(z)
        match box.get("altitude_compare", "less"):
            case "equal":
                return height == wanted
            case "more":
                return height > wanted
            case _:
                return height < wanted

    def _stacked(self, box: Box) -> list[int]:
        found: set[int] = set()
        for pick in _ids(box.get("furni")):
            if pick not in self.furni:
                continue
            item = self.furni[pick]
            for other in self._furni_on_tile(item["x"], item["y"]):
                height, base = _hundredths(self.furni[other]["z"]), _hundredths(item["z"])
                match box.get("stacking", "above"):
                    case "below":
                        keep = height < base
                    case "level":
                        keep = height == base
                    case "tile":
                        keep = True
                    case _:
                        keep = height > base
                if keep:
                    found.add(other)
        return list(found)

    def _matches(self, box: Box, ctx: Context) -> list[int]:
        name = str(box.get("variable", ""))
        match box.classname:
            case "wf_slc_furni_picks":
                return [i for i in _ids(box.get("furni")) if i in self.furni]
            case "wf_slc_furni_bytype":
                types = {self.furni[i]["classname"] for i in _ids(box.get("furni")) if i in self.furni}
                return [i for i, f in self.furni.items() if f["classname"] in types]
            case "wf_slc_furni_signal":
                return list(ctx.signal_furni)
            case "wf_slc_furni_with_var":
                return [i for i in self.furni if f"furni:{i}" in self.variables[name]]
            case "wf_slc_furni_area":
                return [i for i, f in self.furni.items() if self._in_area(box, f["x"], f["y"])]
            case "wf_slc_furni_altitude":
                return [i for i, f in self.furni.items() if self._at_altitude(box, f["z"])]
            case "wf_slc_furni_onfurni":
                return self._stacked(box)
            case "wf_slc_users_team":
                return [u for u in self.users if self._in_team(u, box.get("team", "any"))]
            case "wf_slc_users_signal":
                return list(ctx.signal_users)
            case "wf_slc_users_with_var":
                return [u for u in self.users if f"user:{u}" in self.variables[name]]
            case "wf_slc_users_area":
                return [u for u, d in self.users.items() if self._in_area(box, d["x"], d["y"])]
            case "wf_slc_users_onfurni":
                tiles = {
                    (self.furni[i]["x"], self.furni[i]["y"])
                    for i in _ids(box.get("furni"))
                    if i in self.furni
                }
                return [u for u, d in self.users.items() if (d["x"], d["y"]) in tiles]
            case "wf_slc_users_byname":
                wanted = {n.strip().lower() for n in str(box.get("names", "")).splitlines() if n.strip()}
                return [u for u, d in self.users.items() if d["name"].lower() in wanted]
        return []

    def _users_for(self, box: Box, ctx: Context) -> list[int]:
        source = box.get("user_source", "default")
        if source == "trigger":
            return [ctx.user] if ctx.user is not None else []
        if source == "signal":
            return list(ctx.signal_users)
        if source == "selector":
            return list(ctx.users or [])
        # A real room's default is the triggering user, even with a selector in the stack.
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
        return picks

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

    def _holders(self, box: Box, name: str, ctx: Context) -> list[int | None]:
        """Who a variable box acts on, which follows the kind of variable it has chosen."""
        match self.definitions.get(name, {}).get("scope", "user"):
            case "global" | "context":
                return [None]
            case "furni":
                furni = self._furni_for(box, ctx)
                if not furni and box.get("furni_source", "default") == "default" and ctx.furni is not None:
                    return [ctx.furni]
                return list(furni)
            case _:
                return list(self._users_for(box, ctx))

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
        holders = self._holders(box, name, ctx)
        match box.classname:
            case "wf_cnd_actor_in_team":
                return bool(users) and all(self._in_team(u, box.get("team", "any")) for u in users)
            case "wf_cnd_not_in_team":
                return all(not self._in_team(u, box.get("team", "any")) for u in users)
            case "wf_cnd_var_age_match":
                return bool(holders) and all(
                    self._age_matches(box, self._holding(name, h, ctx)) for h in holders
                )
            case "wf_cnd_has_var":
                return bool(holders) and all(self._holding(name, h, ctx) is not None for h in holders)
            case "wf_cnd_neg_has_var":
                return all(self._holding(name, h, ctx) is None for h in holders)
            case "wf_cnd_var_val_match":
                return bool(users) and all(
                    self._compare(box, self._holding(name, h, ctx), h, ctx) for h in holders
                )
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

    def _age_matches(self, box: Box, holding: Holding | None) -> bool:
        if holding is None:
            return False
        since = holding.updated_ms if box.get("age_of") == "update" else holding.created_ms
        age = self.now_ms - since
        limit = _int(box.get("duration", 0)) * TIME_UNITS.get(str(box.get("unit", "seconds")), 1000)
        match box.get("compare", "less"):
            case "equal":
                return age == limit
            case "more":
                return age > limit
            case _:
                return age < limit

    def _compare(self, box: Box, holding: Holding | None, user: int | None, ctx: Context) -> bool:
        if holding is None:
            return False
        target = self._operand(box, user, ctx)
        if target is None:
            return False
        match box.get("compare", ">"):  # The real box's default.
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

    def _changed(self, name: str, holder: int | None) -> None:
        for stack, box in self._triggers("wf_trg_var_changed"):
            if box.get("variable") == name:
                is_furni = self.definitions.get(name, {}).get("scope") == "furni"
                self._start(
                    stack,
                    Context(trigger=box, furni=holder) if is_furni else Context(trigger=box, user=holder),
                )

    def _holder_label(self, name: str, holder: int | None) -> str:
        scope = self.definitions.get(name, {}).get("scope", "user")
        return f"{scope} {holder}" if holder is not None else f"this {scope} variable"

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
        for user in self._holders(box, name, ctx):
            if self._holding(name, user, ctx) is not None and not box.get("overwrite"):
                continue
            amount = self._operand(box, user, ctx)
            if amount is None:
                continue
            self._write(name, user, Holding(_clamp(amount), self.now_ms, self.now_ms), ctx)
            self._changed(name, user)

    def _do_remove_var(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        for user in self._holders(box, name, ctx):
            if self.definitions.get(name, {}).get("scope") == "context":
                ctx.context_vars.pop(name, None)
            else:
                self.variables[name].pop(self._key(name, user), None)
            self._changed(name, user)

    def _operand(self, box: Box, user: int | None, ctx: Context) -> int | None:
        """The box's value, or what another variable holds for the same holder. None if it holds nothing."""
        reference = str(box.get("from_variable", "")).strip()
        if not reference:
            return _int(box.get("value", 0))
        source = self._holding(reference, user, ctx)
        if source is None:
            self._log(
                "error", f"{reference} is not set for {self._holder_label(reference, user)}", box=box.id
            )
            return None
        return self._read(source, str(box.get("from_field", "value")))

    def _do_change_var_val(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        for user in self._holders(box, name, ctx):
            holding = self._holding(name, user, ctx)
            if holding is None:
                self._log(
                    "error",
                    f"{name} is not set for {self._holder_label(name, user)}, so it was not changed",
                    box=box.id,
                )
                continue
            amount = self._operand(box, user, ctx)
            if amount is None:
                continue
            value = operations.apply(str(box.get("operation", "set")), holding.value, amount, self.random)
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
            if self.furni[furni_id]["classname"] not in NOT_WIRED_TOGGLED:
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

    def _in_team(self, user_id: int, team: Any) -> bool:
        user = self.users.get(user_id)
        if not user or user["team"] is None:
            return False
        return bool(team == "any" or user["team"] == team)

    def _do_join_team(self, box: Box, ctx: Context) -> None:
        team = box.get("team", "red")
        if team in TEAMS:
            for user_id in self._users_for(box, ctx):
                if user_id in self.users:
                    self.users[user_id]["team"] = team
                    self._log("info", f"{self._user_name(user_id)} joined the {team} team")

    def _do_leave_team(self, box: Box, ctx: Context) -> None:
        for user_id in self._users_for(box, ctx):
            if user_id in self.users and self.users[user_id]["team"] is not None:
                self.users[user_id]["team"] = None
                self._log("info", f"{self._user_name(user_id)} left their team")

    def _give_points(self, box: Box, team: Any, scorer: int | None) -> None:
        """Points only count during a game, and a team's score never goes below 0."""
        if team not in TEAMS:
            return
        if not self.game_running:
            self._log("info", "No game is running, so no points were given", box=box.id)
            return
        times = max(0, min(_int(box.get("times")), MAX_TIMES))
        if times and self.score_grants[(box.id, scorer)] >= times:
            return
        self.score_grants[(box.id, scorer)] += 1
        points = max(-MAX_POINTS, min(_int(box.get("points", 5), 5), MAX_POINTS))
        self.team_scores[team] = max(0, self.team_scores[team] + points)
        self._log("info", f"The {team} team has {self.team_scores[team]} points")

    def _do_give_score(self, box: Box, ctx: Context) -> None:
        for user_id in self._users_for(box, ctx):
            if user_id in self.users and self.users[user_id]["team"] is not None:
                self._give_points(box, self.users[user_id]["team"], user_id)

    def _do_give_score_tm(self, box: Box, _ctx: Context) -> None:
        self._give_points(box, box.get("team", "red"), None)

    def _off_map(self, x: int, y: int) -> bool:
        if x < 0 or y < 0:
            return True
        return self.room_size is not None and (x >= self.room_size[0] or y >= self.room_size[1])

    def _shift_furni(self, furni_id: int, dx: int, dy: int) -> bool:
        """A move off the room or onto a user cannot be made, and the furni stays put."""
        item = self.furni[furni_id]
        x, y = item["x"] + dx, item["y"] + dy
        if self._off_map(x, y) or any((u["x"], u["y"]) == (x, y) for u in self.users.values()):
            return False
        item["x"], item["y"] = x, y
        return True

    def _furni_step(self, direction: str) -> tuple[int, int]:
        match direction:
            case "random":
                return self.random.choice(list(MOVES.values()))
            case "random_x":
                return self.random.choice((MOVES["x+"], MOVES["x-"]))
            case "random_y":
                return self.random.choice((MOVES["y+"], MOVES["y-"]))
        return MOVES.get(direction, (0, 0))

    def _do_move_rotate(self, box: Box, ctx: Context) -> None:
        for furni_id in self._furni_for(box, ctx):
            item = self.furni[furni_id]
            dx, dy = self._furni_step(str(box.get("direction", "none")))
            if (dx or dy) and not self._shift_furni(furni_id, dx, dy):
                continue
            rotation = str(box.get("rotation", "none"))
            turn = {"clockwise": 2, "counterclockwise": -2}.get(rotation, 0)
            if rotation == "random":
                turn = self.random.choice((0, 2, 4, 6))
            item["rot"] = (item["rot"] + turn) % 8

    def _do_rel_mov(self, box: Box, ctx: Context) -> None:
        dx, dy = _int(box.get("move_x")), _int(box.get("move_y"))
        if dx or dy:
            for furni_id in self._furni_for(box, ctx):
                self._shift_furni(furni_id, dx, dy)

    def _do_set_altitude(self, box: Box, ctx: Context) -> None:
        amount = _hundredths(box.get("altitude"))
        change = str(box.get("altitude_change", "raise"))
        for furni_id in self._furni_for(box, ctx):
            item = self.furni[furni_id]
            current = _hundredths(item["z"])
            wanted = {"lower": current - amount, "set": amount}.get(change, current + amount)
            item["z"] = max(0, min(wanted, MAX_ALTITUDE)) / 100

    def _do_furni_to_user(self, box: Box, ctx: Context) -> None:
        users = [u for u in self._users_for(box, ctx) if u in self.users]
        if users:
            target = self.users[users[0]]
            for furni_id in self._furni_for(box, ctx):
                self.furni[furni_id]["x"], self.furni[furni_id]["y"] = target["x"], target["y"]

    def _do_furni_to_furni(self, box: Box, ctx: Context) -> None:
        targets = [i for i in _ids(box.get("furni")) if i in self.furni]
        if not targets:
            return
        match box.get("furni_source", "default"):
            case "signal":
                movers = list(ctx.signal_furni)
            case "selector":
                movers = list(ctx.selected_furni or [])
            case _:
                movers = [ctx.furni] if ctx.furni is not None else []
        target = self.furni[self.random.choice(targets)]
        for furni_id in movers:
            item = self.furni[furni_id]
            self._shift_furni(furni_id, target["x"] - item["x"], target["y"] - item["y"])

    def _do_move_rotate_user(self, box: Box, ctx: Context) -> None:
        step = MOVES.get(str(box.get("user_move", "none")))
        turn = str(box.get("user_turn", "none"))
        for user_id in self._users_for(box, ctx):
            user = self.users.get(user_id)
            if not user:
                continue
            if step and not self._off_map(user["x"] + step[0], user["y"] + step[1]):
                self._move_user(user_id, user["x"] + step[0], user["y"] + step[1])
            if turn in MOVES:
                user["dir"] = list(MOVES).index(turn)
            elif turn in ("clockwise", "counterclockwise"):
                user["dir"] = (_int(user["dir"]) + (1 if turn == "clockwise" else -1)) % 8

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

    def view_defined(self) -> list[dict[str, str]]:
        """Variables a box defines that nothing holds yet. A real room lists these by definition too."""
        return [
            {"variable": name, "scope": definition["scope"]}
            for name, definition in sorted(self.definitions.items())
            if not self.variables.get(name)
        ]

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
            "defined_variables": self.view_defined(),
            "game": {"running": self.game_running, "scores": dict(self.team_scores)},
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
