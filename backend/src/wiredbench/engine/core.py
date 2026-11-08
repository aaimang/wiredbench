"""A deterministic WIRED simulator.

The same room, seed and inputs always give the same result, so runs can be replayed. Time is virtual and
advances only when asked. Room data is untrusted, so bad settings produce a trace line and never an
exception.
"""

from __future__ import annotations

import heapq
import math
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from wiredbench.engine import interactions, internal, neighbourhood, operations
from wiredbench.engine.boxes import ANIM_MAX_MS, ANIM_MIN_MS, BOXES, CURVE_LIMIT, TIME_UNITS

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
DEFAULT_TIMEZONE = "Europe/London"  # What a real room showed before anyone set one.
# Avatar details that are numbers, or flags that exist only while they are true.
USER_DETAILS = {
    "@gender",
    "@level",
    "@achievement_score",
    "@handitem",
    "@effect",
    "@dance",
    "@sign",
    "@habbicon",
    "@favourite_group_id",
    "@is_hc",
    "@has_rights",
    "@is_group_admin",
    "@is_owner",
    "@is_frozen",
    "@is_muted",
    "@is_idle",
}
ADDABLE_DETAILS = {"@handitem", "@habbicon"}  # The two a real room lets Give Variable create.
SIGN_MS = 5000  # A real room holds a sign for a few seconds. The exact length is assumed.
# How long a user counts as doing an expression, for Users by Action. Others count until they stop.
EXPRESSION_MS = {"wave": 5000, "blow": 1400, "jump": 700, "laugh": 2000, "respect": 2000}
SEAT_TURN_BACK_MS = (
    500  # A real room turns a seated user back within about a second. The exact length is assumed.
)
TEAM_TYPES = ("wired", "banzai", "freeze")
TEAM_TYPE_NUMBERS = {"banzai": 0, "freeze": 1, "wired": 4}  # A real room read 0 for a Battle Banzai team.
CHANGE_CREATED, CHANGE_VALUE, CHANGE_DELETED = 0, 1, 2
ORIGIN_INSPECTION = 2
FURNI_FACTS = {
    "@dimensions.x": "xdim",
    "@dimensions.y": "ydim",
    "@can_stand_on": "can_stand",
    "@can_sit_on": "can_sit",
    "@can_lay_on": "can_lay",
    "@is_stackable": "stackable",
}
DEFAULT_FLIGHT_MS = 500  # A real room took about this long for 3 tiles, with or without the add-on.
MAX_FLIGHT_MS = 60_000
NEGATIVE = "wf_act_neg_"
MAX_FX_PER_VARIABLE = 5  # A real room saves a sixth but never draws it.
CLOCK_TICK_MS = 500
GAME_TIMERS = {"bb_counter", "fball_counter", "es_counter"}
DEFAULT_GAME_SECONDS = 30
MAX_TIMES = 10
# A real room leaves these as they are when Toggle Furni State points at them.
NOT_WIRED_TOGGLED = {"wf_floor_switch1", "wf_floor_switch2"}
# Bots walk a tile every half second, as users do. Bot Teleport's times are from a real room.
BOT_STEP_MS = 500
BOT_TELEPORT_EFFECT = 4
BOT_ARRIVE_MS, BOT_EFFECT_OFF_MS = 1500, 3100
MAX_BOT_SEARCH = 64 * 64
FIGURE = re.compile(r"[a-z]{2}-\d{1,6}(-\d{1,6}){0,3}(\.[a-z]{2}-\d{1,6}(-\d{1,6}){0,3}){0,24}")
FREEZE_EFFECTS = {218, 12, 11, 53, 163}  # The effects Freeze offers.
LINK = "wf_link"
LINK_MESSAGE_BYTES = 1000  # Habbo refuses a longer link message.
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


def _zone(name: Any) -> tzinfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TIMEZONE))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return UTC


def _three_way(compare: Any, value: int, reference: int) -> bool:
    if compare == "equal":
        return value == reference
    return value > reference if compare == "more" else value < reference


def _in_range(value: int, low: int, high: int) -> bool:
    return low <= value <= high if low <= high else value >= low or value <= high


def _hundredths(value: Any) -> int:
    """Heights compare in hundredths of a tile, which is as fine as a box can state them."""
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError, OverflowError):
        return 0


@dataclass
class Clock:
    """A wired counter. It counts up in half seconds, and its furni state shows whole seconds."""

    half_seconds: int
    game_aware: bool
    running: bool = False
    started: bool = False
    stopped: bool = False
    run: int = 0


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


CLICK_TILE = "room_invisible_click_tile"
# Chase and Flee notice a user this many tiles away, on the furni's row or column only.
NOTICE_RANGE = 3
# The tile one step away in each of the eight directions, 0 being y-.
DIRECTION_STEPS = {
    0: (0, -1),
    1: (1, -1),
    2: (1, 0),
    3: (1, 1),
    4: (0, 1),
    5: (-1, 1),
    6: (-1, 0),
    7: (-1, -1),
}
STEP_DIRECTIONS = {step: direction for direction, step in DIRECTION_STEPS.items()}
CARDINAL_STEPS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _action_number_matches(box: Box | None, value: int) -> bool:
    """A sign or dance number in the box's text must match; an empty text matches any."""
    text = str(box.get("text", "") if box else "").strip().lower().removeprefix("dance").strip()
    return not text.lstrip("-").isdigit() or int(text) == value


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
    event: dict[str, int] = field(default_factory=dict)
    # What the trigger said or received, for $(trigger_text). None when it carried no text.
    text: str | None = None


class Engine:
    def __init__(
        self,
        document: dict[str, Any],
        heights: dict[str, float] | None = None,
        seed: int = 1,
        tick_ms: int = TICK_MS,
        furni_states: dict[str, list[int]] | None = None,
        not_standable: set[str] | None = None,
        furni_facts: dict[str, dict[str, Any]] | None = None,
        clock_start_ms: int = 0,
        room_id: int = 0,
    ) -> None:
        self.seed = seed
        self.furni_facts = furni_facts or {}
        self.clock_start_ms = clock_start_ms
        self.room_id = room_id
        self.not_standable = not_standable or set()
        self.tick_ms = tick_ms
        self.furni_states = furni_states or {}
        self.random = random.Random(seed)  # noqa: S311 - Replays need a seed; this is not for security.
        self.now_ms = 0
        self.heights = heights or {}
        # Each dice's latest roll, so an older roll that lands late is ignored.
        self.dice_turns: dict[int, int] = {}
        self.furni: dict[int, dict[str, Any]] = {}
        self.users: dict[int, dict[str, Any]] = {}
        self.boxes_at: dict[tuple[int, int], list[Box]] = defaultdict(list)
        self.variables: dict[str, dict[str, Holding]] = defaultdict(dict)
        self.definitions: dict[str, dict[str, Any]] = {}
        # Bots: where each one walks, whom it follows, and whether it has caught up with them.
        self.bot_walks: dict[int, dict[str, Any]] = {}
        self.bot_follows: dict[int, int] = {}
        self.bot_caught: dict[int, bool] = {}
        self.bot_turns: dict[int, int] = {}
        # Freeze: the effect each frozen user wore before, and who a WIRED teleport thaws.
        self.before_freeze: dict[int, int | None] = {}
        self.thaw_on_teleport: set[int] = set()
        # Random add-on: the effects each one picked in its recent runs.
        self.random_picks: dict[int, deque[list[int]]] = {}
        # Echo variables, by name, and the variable each one mirrors. Pointer variables, by name.
        self.echoes: dict[str, str] = {}
        self.pointers: dict[str, Box] = {}
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
        self.last_context: Context | None = None  # Only for the inspection window.
        self.actions_this_advance = 0
        self.messages: list[dict[str, Any]] = []
        self.box_runs: dict[int, int] = defaultdict(int)
        self.stack_work: dict[str, int] = defaultdict(int)
        self.log_counts: dict[str, int] = defaultdict(int)
        self.game_running = False
        self.team_scores = dict.fromkeys(TEAMS, 0)
        self.clocks: dict[int, Clock] = {}
        self.flights: list[dict[str, Any]] = []
        self.projectile_values: dict[int, dict[str, int]] = {}
        self.furni_looks: dict[int, dict[str, Any]] = {}
        self.user_looks: dict[int, dict[str, Any]] = {}
        self.sign_turns: dict[int, int] = {}
        self.expressions: dict[int, tuple[str, int]] = {}  # A user's last expression and when.
        self.headings: dict[tuple[int, int], int] = {}  # Move to Direction and Flee: the way a furni goes.
        self.game_timer: int | None = None
        self.game_timer_run = 0
        self.score_grants: dict[tuple[int, int | None], int] = defaultdict(int)
        self.problems: deque[dict[str, Any]] = deque(maxlen=PROBLEMS_KEPT)
        self._load(document)

    # --- Loading ---

    def _load(self, document: dict[str, Any]) -> None:
        room = document.get("room")
        self.timezone = _zone(room.get("timezone") if isinstance(room, dict) else None)
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
            if isinstance(raw.get("link"), int):
                item["link"] = raw["link"]  # A teleport's partner.
            self.furni[item["id"]] = item
            game_counter = raw["classname"].startswith("wf_game_upcounter")
            if game_counter or raw["classname"].startswith("wf_upcounter"):
                seconds = max(0, _int(item["state"]))
                self.clocks[item["id"]] = Clock(seconds * 2, game_counter, started=seconds > 0)
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
        # Place Furni copies what its picks looked like when the room started.
        self.templates = {i: dict(item) for i, item in self.furni.items()}
        self.next_furni_id = max(self.furni, default=0) + 1
        for stack in self.stacks:
            for box in stack.boxes:
                self._define_variable(box)
        for stack in self.stacks:
            for box in stack.boxes:
                self._define_stand_in(box)
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
                "team_type": "wired",
                "details": dict(raw["details"]) if isinstance(raw.get("details"), dict) else {},
            }
            if raw.get("bot"):
                self.users[raw["id"]] |= {"bot": True, "figure": str(raw.get("figure", ""))}
        self._seat_users()
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

    def _define_stand_in(self, box: Box) -> None:
        """Echo and Pointer variables stand in for other variables, so they are set up after those."""
        name = str(box.get("variable", "")).strip()
        if not name or name in self.definitions:
            return
        if box.classname == "wf_var_echo":
            source = self.echoes.get(str(box.get("source", "")).strip(), str(box.get("source", "")).strip())
            if source in self.definitions and source != name:
                # Reads and writes go to the source, so both names share its scope and its values.
                self.echoes[name] = source
                self.definitions[name] = self.definitions[source]
                self.variables[name] = self.variables[source]
        elif box.classname == "wf_var_pointer":
            self.pointers[name] = box
            self.definitions[name] = {"scope": str(box.get("target", "user")), "time": False}

    def _pointed(self, name: str, ctx: Context | None) -> str | None:
        """The variable a pointer stands for: the variable box whose furni id its context accessor holds."""
        box = self.pointers[name]
        accessor = str(box.get("accessor", "")).strip()
        if self.definitions.get(accessor, {}).get("scope") != "context" or ctx is None:
            return None
        held = ctx.context_vars.get(accessor)
        target = self.stack_of.get(held.value) if held is not None else None
        found = next((b for b in target.boxes if b.id == held.value), None) if target and held else None
        if found is None or found.classname == "wf_var_pointer" or not found.classname.startswith("wf_var_"):
            return None
        pointed = str(found.get("variable", "")).strip()
        if self.definitions.get(pointed, {}).get("scope") != self.definitions[name]["scope"]:
            return None
        return pointed

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
            if self._frozen(_int(user)):
                self._log("info", f"{self._user_name(_int(user))} is frozen and cannot walk")
                return
            if entry.get("dir") is not None and (who := self.users.get(_int(user))) is not None:
                who["dir"] = _int(entry["dir"]) % 8
            self._move_user(_int(user), _int(entry.get("x")), _int(entry.get("y")))
        elif kind == "game_start":
            self._game_start()
        elif kind == "game_end":
            self._game_end()
        elif kind == "box_settings":
            # A real room saves a box's settings only for its owner or a user with rights.
            if user is None or self._has_rights(_int(user)):
                self._edit_box(_int(entry.get("furni")), entry.get("settings"))
            else:
                self._log("info", "Only the owner or a user with rights can change a box")
        elif kind == "move_furni":
            self._move_by_hand(_int(user), entry)
        elif kind == "user_detail":
            who = self.users.get(_int(user))
            if who is not None and entry.get("detail") in USER_DETAILS:
                if entry.get("amount") is None:  # Such as a sign being put down.
                    who["details"].pop(entry["detail"], None)
                else:
                    who["details"][entry["detail"]] = _clamp(_int(entry["amount"]))
                    self._detail_action(who["id"], entry["detail"], who["details"][entry["detail"]])
                    if entry["detail"] == "@sign":
                        self.sign_turns[who["id"]] = self.sign_turns.get(who["id"], 0) + 1
                        turn = self.sign_turns[who["id"]]
                        self._push(self.now_ms + SIGN_MS, "sign_end", {"user": who["id"], "turn": turn})
        elif kind == "turn":
            if (who := self.users.get(_int(user))) is not None:
                who["dir"] = _int(entry.get("dir")) % 8
                self._turn_back_later()
        elif kind == "say":
            self._say(_int(user), str(entry.get("text", ""))[:500])
        elif kind == "click":
            self._click(_int(user), _int(entry.get("furni")))
        elif kind == "click_user":
            self._click_user(_int(user), _int(entry.get("target")))
        elif kind == "action":
            if _int(user) in self.users and str(entry.get("text")) in EXPRESSION_MS:
                self._perform(_int(user), str(entry["text"]), 0)
        elif kind == "use":
            self._use(_int(user), _int(entry.get("furni")))
        elif kind == "dice_off":
            self._close_dice(_int(user), _int(entry.get("furni")))
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
        elif kind == "set_value":
            self._set_value(str(entry.get("variable", "")), str(entry.get("key", "")), entry.get("value"))
        elif kind == "api_delete":
            self.variables[str(entry["variable"])].pop(str(entry["key"]), None)
        self._drain()

    def _set_value(self, name: str, key: str, raw: Any) -> None:
        """A value typed into the run panel. It acts like a change from a box, so stacks react to it."""
        if key not in self.variables.get(name, {}):
            return
        value = max(INT64_MIN, min(_int(raw), INT64_MAX))
        before = self.variables[name][key].value
        self._store(name, key, value)
        self._log("info", f"{name} was set to {value} by hand")
        holder, _, entity = key.partition(":")
        self._changed(
            name,
            _int(entity) if holder in ("user", "furni") else None,
            before,
            value,
            CHANGE_VALUE,
            ORIGIN_INSPECTION,
        )

    def _store(self, name: str, key: str, value: int) -> None:
        holding = self.variables[name].get(key)
        if holding:
            holding.value = value
            holding.updated_ms = self.now_ms
        else:
            self.variables[name][key] = Holding(value, self.now_ms, self.now_ms)

    def _furni_on_tile(self, x: int, y: int) -> list[int]:
        return [i for i, f in self.furni.items() if f["x"] == x and f["y"] == y]

    def _posture(self, x: int, y: int) -> str:
        """What a user on a tile does: sit on a seat, lay on a bed, or stand."""
        top = self._top_furni(x, y)
        facts = self.furni_facts.get(top["classname"], {}) if top else {}
        return "sit" if facts.get("can_sit") else "lay" if facts.get("can_lay") else "std"

    def _covering(self, x: int, y: int) -> list[int]:
        """Every furni whose footprint covers a tile."""
        found = []
        for furni_id, item in self.furni.items():
            facts = self.furni_facts.get(item["classname"], {})
            width, depth = facts.get("xdim", 1), facts.get("ydim", 1)
            if item["rot"] in (2, 6):
                width, depth = depth, width
            if item["x"] <= x < item["x"] + width and item["y"] <= y < item["y"] + depth:
                found.append(furni_id)
        return found

    def _top_furni(self, x: int, y: int) -> dict[str, Any] | None:
        top: dict[str, Any] | None = None
        for furni_id in self._covering(x, y):
            item = self.furni[furni_id]
            if top is None or item["z"] >= top["z"]:
                top = item
        return top

    def _seat_rotation(self, x: int, y: int) -> int | None:
        """The rotation of the seat or bed on top of a tile, which a user on it faces."""
        top = self._top_furni(x, y)
        if top is None:
            return None
        facts = self.furni_facts.get(top["classname"], {})
        rot = _int(top["rot"]) % 8
        # Habbo never seats anyone diagonally: they face the direction before.
        return rot - rot % 2 if facts.get("can_sit") or facts.get("can_lay") else None

    def _seat_users(self) -> None:
        """A user sitting or lying faces the way the furni is turned, as in a real room.

        A change of posture is an action others see, for User Performs Action. The first look at a
        user, as the room starts, is not a change.
        """
        changed: list[tuple[int, str]] = []
        for user in self.users.values():
            seat = self._seat_rotation(user["x"], user["y"])
            if seat is not None:
                user["dir"] = seat
            pose = self._posture(user["x"], user["y"])
            if user.get("pose") not in (None, pose):
                changed.append((user["id"], {"std": "stand"}.get(pose, pose)))
            user["pose"] = pose
        for user_id, action in changed:
            self._perform(user_id, action, 0)

    def _turn_back_later(self) -> None:
        """A real room lets a seated user turn for a moment, then turns them back to the seat."""
        if any(
            (seat := self._seat_rotation(user["x"], user["y"])) is not None and user["dir"] != seat
            for user in self.users.values()
        ):
            self._push(self.now_ms + SEAT_TURN_BACK_MS, "seat_turn_back", {})

    def _move_user(self, user_id: int, x: int, y: int) -> None:
        user = self.users.get(user_id)
        if not user:
            return
        left = self._furni_on_tile(user["x"], user["y"])
        user["x"], user["y"] = x, y
        self._seat_users()
        for furni in left:
            self._fire("wf_trg_walks_off_furni", user=user_id, furni=furni)
        for furni in self._furni_on_tile(x, y):
            self._fire("wf_trg_walks_on_furni", user=user_id, furni=furni)

    def _say(self, user_id: int, text: str) -> None:
        if user_id not in self.users:
            return
        self._log("info", f"{self.users[user_id]['name']} says: {text}")
        owner = bool(_int(self.users[user_id]["details"].get("@is_owner")))
        fired = []
        for stack, box in self._triggers("wf_trg_says_something"):
            if box.get("owner_only") and not owner:
                continue
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
                fired.append((stack, box))
        # A box that hides the triggerer's message keeps it out of the room's chat.
        if any(box.get("hide_message", True) for _, box in fired):
            self._log("info", "The message was hidden from the room")
        else:
            name = self.users[user_id]["name"]
            self.messages.append(
                {"at_ms": self.now_ms, "user": None, "speaker": user_id, "text": f"{name}: {text}"}
            )
        for stack, box in fired:
            self._start(stack, Context(trigger=box, user=user_id, event={"@event.chat.type": 0}, text=text))

    def _click(self, user_id: int, furni_id: int) -> None:
        if furni_id in self.furni:
            self._fire("wf_trg_click_furni", user=user_id, furni=furni_id)
            if self.furni[furni_id]["classname"] == CLICK_TILE:
                self._fire("wf_trg_click_tile", user=user_id, furni=furni_id)

    def _click_user(self, user_id: int, target: int) -> None:
        """One user clicks another. Effects reach the clicked user through Users from: Selector."""
        clicker, clicked = self.users.get(user_id), self.users.get(target)
        if clicker is None or clicked is None or user_id == target:
            return
        for stack, box in self._triggers("wf_trg_click_user"):
            dx, dy = clicked["x"] - clicker["x"], clicked["y"] - clicker["y"]
            if not box.get("keep_facing") and (dx or dy):
                clicker["dir"] = round(math.atan2(dx, -dy) / (math.pi / 4)) % 8
            self._start(stack, Context(trigger=box, user=user_id, users=[target]))

    def _perform(self, user_id: int, action: str, value: int) -> None:
        """A user does something others can see, such as waving or holding up a sign."""
        if action in EXPRESSION_MS:
            self.expressions[user_id] = (action, self.now_ms)
        for stack, box in self._triggers("wf_trg_user_performs_action"):
            if box.get("action", "wave") == action and _action_number_matches(box, value):
                self._start(stack, Context(trigger=box, user=user_id))

    def _detail_action(self, user_id: int, detail: str, value: int) -> None:
        if detail == "@sign":
            self._perform(user_id, "sign", value)
        elif detail == "@dance" and value > 0:
            self._perform(user_id, "dance", value)
        elif detail == "@is_idle" and value:
            self._perform(user_id, "sleep", value)

    def _performing(self, user_id: int, action: str, box: Box) -> bool:
        """Whether a user is doing an action now, as Users by Action checks it."""
        user = self.users[user_id]
        details = user["details"]
        if action in EXPRESSION_MS:
            last = self.expressions.get(user_id)
            return last is not None and last[0] == action and self.now_ms - last[1] < EXPRESSION_MS[action]
        match action:
            case "sit" | "lay":
                return user.get("pose") == action
            case "stand":
                return user.get("pose") not in ("sit", "lay")
            case "sleep":
                return bool(details.get("@is_idle"))
            case "awake":
                return not details.get("@is_idle")
            case "sign":
                return "@sign" in details and _action_number_matches(box, _int(details["@sign"]))
            case "dance":
                dance = _int(details.get("@dance"))
                return dance > 0 and _action_number_matches(box, dance)
        return False

    def _score_changed(self, team: str, before: int, scorer: int | None) -> None:
        """Score Achieved fires once, when a team's score goes up past the box's mark."""
        after = self.team_scores[team]
        for stack, box in self._triggers("wf_trg_score_achieved"):
            mark = max(1, _int(box.get("points", 100), 100))
            if box.get("team", "any") not in ("any", team) or not before < mark <= after:
                continue
            self._start(
                stack, Context(trigger=box, user=scorer, users=[scorer] if scorer is not None else None)
            )

    def _use(self, user_id: int, furni_id: int) -> None:
        item = self.furni.get(furni_id)
        if item is None:
            return
        kind = interactions.kind_of(
            item["classname"], self.furni_facts.get(item["classname"], {}).get("category")
        )
        who = self.users.get(user_id)
        # A real room checks who may use a furni and, for some, that they stand next to it.
        if who is not None and furni_id not in self.clocks and item["classname"] not in GAME_TIMERS:
            if not interactions.anyone_may_use(kind) and not self._has_rights(user_id):
                self._log(
                    "info", f"Only the owner or a user with rights can use {self._name(item['classname'])}"
                )
                return
            if interactions.needs_to_be_next_to(kind) and not interactions.next_to(
                (who["x"], who["y"]), (item["x"], item["y"])
            ):
                self._log(
                    "info", f"{who['name']} must stand next to {self._name(item['classname'])} to use it"
                )
                return
        if interactions.used_from_front(kind) and who is not None:
            if (who["x"], who["y"]) != interactions.front_of(item["x"], item["y"], item["rot"]):
                self._log("info", f"{who['name']} must stand in front of {self._name(item['classname'])}")
                return
            if kind == "teleport":
                self._enter_teleport(user_id, furni_id)
            elif kind == "one_way_gate":
                self._pass_one_way(user_id, furni_id)
            else:
                self._vend(user_id, furni_id)
        elif kind == "vending":
            self._vend(None, furni_id)  # With nobody using it, it only plays its animation.
        elif kind == "gate" and item["state"] != 0 and self._someone_on(item["x"], item["y"]):
            # A real room does not close a gate on someone standing in it.
            self._log("info", f"{self._name(item['classname'])} cannot close while someone stands in it")
            return
        elif kind == "dice":
            self._roll_dice(furni_id)
        elif furni_id in self.clocks:
            clock = self.clocks[furni_id]
            if clock.running:
                clock.running = False
            else:
                self._clock_run(furni_id, clock)
        elif furni_id in self.furni and self.furni[furni_id]["classname"] in GAME_TIMERS:
            self._use_game_timer(furni_id)
        elif furni_id in self.furni:
            self._set_state(furni_id, self._next_state(furni_id))
        if furni_id in self.furni:
            self._fire("wf_trg_state_changed", user=user_id, furni=furni_id)

    def _someone_on(self, x: int, y: int) -> bool:
        return any(u["x"] == x and u["y"] == y for u in self.users.values())

    def _enter_teleport(self, user_id: int, furni_id: int) -> None:
        """The user steps in, the door flashes, and they come out of the linked teleport."""
        item = self.furni[furni_id]
        partner = item.get("link")
        if partner not in self.furni or partner == furni_id:
            self._log("info", f"{self._name(item['classname'])} is not linked to another teleport")
            return
        if item["state"] != 0 or self._someone_on(item["x"], item["y"]):
            return  # Busy: someone is already going through.
        self._set_state(furni_id, interactions.TELEPORT_OPEN)
        self._move_user(user_id, item["x"], item["y"])
        start = self.now_ms
        payload = {"user": user_id, "from": furni_id, "to": partner}
        for at, phase in (
            (interactions.TELEPORT_FLASH_AT_MS, "flash"),
            (interactions.TELEPORT_ARRIVE_AT_MS, "arrive"),
            (interactions.TELEPORT_OUT_AT_MS, "out"),
            (interactions.TELEPORT_CLOSE_AT_MS, "close"),
        ):
            self._push(start + at, "teleport", {**payload, "phase": phase})

    def _teleport_step(self, payload: dict[str, Any]) -> None:
        user, start, end = payload["user"], self.furni.get(payload["from"]), self.furni.get(payload["to"])
        if start is None or end is None or user not in self.users:
            return
        match payload["phase"]:
            case "flash":
                self._set_state(payload["from"], interactions.TELEPORT_FLASH)
            case "arrive":
                self._set_state(payload["from"], 0)
                self._set_state(payload["to"], interactions.TELEPORT_FLASH)
                self._move_user(user, end["x"], end["y"])
                self.users[user]["dir"] = end["rot"] % 8
            case "out":
                self._set_state(payload["to"], interactions.TELEPORT_OPEN)
                x, y = interactions.front_of(end["x"], end["y"], end["rot"])
                if self._free_tile(x, y):
                    self._move_user(user, x, y)
            case "close":
                self._set_state(payload["to"], 0)

    def _pass_one_way(self, user_id: int, furni_id: int) -> None:
        """A one-way gate opens and lets the user through from its front to its back."""
        item = self.furni[furni_id]
        x, y = interactions.back_of(item["x"], item["y"], item["rot"])
        if item["state"] != 0 or not self._free_tile(x, y):
            return
        self._set_state(furni_id, 1)
        self._move_user(user_id, item["x"], item["y"])
        payload = {"user": user_id, "furni": furni_id, "x": x, "y": y}
        self._push(self.now_ms + interactions.ONE_WAY_THROUGH_MS, "one_way_through", payload)
        self._push(self.now_ms + interactions.ONE_WAY_CLOSE_MS, "one_way_close", payload)

    def _vend(self, user_id: int | None, furni_id: int) -> None:
        """The user turns to the machine, it shows its giving state, and hands over a random item."""
        item = self.furni[furni_id]
        if item["state"] != 0:
            return  # Busy giving to someone else.
        if user_id is not None:
            self.users[user_id]["dir"] = (item["rot"] + 4) % 8
        self._set_state(furni_id, interactions.VENDING_GIVING)
        payload = {"user": user_id, "furni": furni_id}
        self._push(self.now_ms + interactions.VENDING_GIVE_MS, "vend", payload)

    def _vend_give(self, user_id: int | None, furni_id: int) -> None:
        if furni_id not in self.furni:
            return
        self._set_state(furni_id, 0)
        user = self.users.get(user_id) if user_id is not None else None
        if user is None:
            return
        choices = interactions.hand_items(self.furni[furni_id]["classname"])
        if not choices:
            self._log(
                "info", f"Wiredbench does not know what {self._name(self.furni[furni_id]['classname'])} gives"
            )
            return
        user["details"]["@handitem"] = self.random.choice(choices)

    def _free_tile(self, x: int, y: int) -> bool:
        """Inside the room, with nobody on it and nothing on it that cannot be stood on."""
        if self.room_size and not (0 <= x < self.room_size[0] and 0 <= y < self.room_size[1]):
            return False
        if self._someone_on(x, y):
            return False
        return all(self.furni[i]["classname"] not in self.not_standable for i in self._furni_on_tile(x, y))

    def _roll_dice(self, furni_id: int) -> None:
        """A dice shows its rolling animation, then lands on a random face."""
        item = self.furni[furni_id]
        if item["state"] == interactions.DICE_ROLLING:
            return
        self._set_state(furni_id, interactions.DICE_ROLLING)
        self.dice_turns[furni_id] = self.dice_turns.get(furni_id, 0) + 1
        face = self.random.choice(interactions.DICE_FACES)
        payload = {"furni": furni_id, "face": face, "turn": self.dice_turns[furni_id]}
        self._push(self.now_ms + interactions.DICE_ROLL_MS, "dice_land", payload)

    def _close_dice(self, user_id: int, furni_id: int) -> None:
        """Closing a dice puts it back to its blank face, for a user standing next to it."""
        item, who = self.furni.get(furni_id), self.users.get(user_id)
        if item is None or interactions.kind_of(item["classname"], None) != "dice":
            return
        if who is not None and not interactions.next_to((who["x"], who["y"]), (item["x"], item["y"])):
            self._log("info", f"{who['name']} must stand next to {self._name(item['classname'])} to use it")
            return
        self.dice_turns[furni_id] = self.dice_turns.get(furni_id, 0) + 1  # A roll in flight no longer lands.
        self._set_state(furni_id, interactions.DICE_CLOSED)

    def _has_rights(self, user_id: int) -> bool:
        """Whether a user may move furni and change boxes, as the room's owner or with rights."""
        who = self.users.get(user_id)
        details = who["details"] if who else {}
        return bool(_int(details.get("@has_rights")) or _int(details.get("@is_owner")))

    def _move_by_hand(self, user_id: int, entry: dict[str, Any]) -> None:
        """A user with rights moves or turns a furni, as from the furni menu in a real room."""
        item = self.furni.get(_int(entry.get("furni")))
        if item is None:
            return
        if not self._has_rights(user_id):
            self._log("info", "Only the owner or a user with rights can move furni")
            return
        x, y = _int(entry.get("x", item["x"])), _int(entry.get("y", item["y"]))
        if self.room_size and not (0 <= x < self.room_size[0] and 0 <= y < self.room_size[1]):
            return
        item["x"], item["y"] = x, y
        if entry.get("rot") is not None:
            item["rot"] = _int(entry["rot"]) % 8
        if entry.get("z") is not None:
            item["z"] = max(0.0, min(float(entry["z"]), MAX_ALTITUDE / 100))
        name = self.users[user_id]["name"]
        self._log("info", f"{name} moved {self._name(item['classname'])}")

    def _edit_box(self, box_id: int, settings: Any) -> None:
        """A real room uses a box's new settings as soon as it is saved, so a run does too."""
        stack = self.stack_of.get(box_id)
        box = next((b for b in stack.boxes if b.id == box_id), None) if stack else None
        if box is not None and isinstance(settings, dict):
            box.settings = settings
            self._log("info", f"{self._name(box.classname)} was changed")

    def _use_game_timer(self, furni_id: int) -> None:
        if self.game_timer == furni_id:
            self._game_end()
            return
        item = self.furni[furni_id]
        item["state"] = max(0, _int(item["state"])) or DEFAULT_GAME_SECONDS
        self.game_timer = furni_id
        self.game_timer_run += 1
        self._push(self.now_ms + 1000, "game_timer", {"furni": furni_id, "run": self.game_timer_run})
        if not self.game_running:
            self._game_start()

    def _game_timer_tick(self, furni_id: int, run: int) -> None:
        if self.game_timer != furni_id or run != self.game_timer_run:
            return
        item = self.furni[furni_id]
        item["state"] = max(0, _int(item["state"]) - 1)
        if item["state"] == 0:
            self._game_end()
        else:
            self._push(self.now_ms + 1000, "game_timer", {"furni": furni_id, "run": run})

    def _clock_run(self, furni_id: int, clock: Clock) -> None:
        if clock.running:
            return
        clock.running, clock.started, clock.stopped = True, True, False
        clock.run += 1
        # The count follows the room's half second cycle, not the moment it was started.
        due = (self.now_ms // CLOCK_TICK_MS + 1) * CLOCK_TICK_MS
        self._push(due, "clock", {"furni": furni_id, "run": clock.run})
        if clock.game_aware and not self.game_running:
            self._game_start()

    def _clock_tick(self, furni_id: int, run: int) -> None:
        clock = self.clocks.get(furni_id)
        if clock is None or not clock.running or clock.run != run:
            return
        clock.half_seconds += 1
        self._clock_show(furni_id, clock)
        self._push(self.now_ms + CLOCK_TICK_MS, "clock", {"furni": furni_id, "run": run})
        for stack, box in self._triggers("wf_trg_clock_counter"):
            if furni_id in _ids(box.get("furni")) and self._clock_target(box) == clock.half_seconds:
                self._start(stack, Context(trigger=box, furni=furni_id))

    def _clock_show(self, furni_id: int, clock: Clock) -> None:
        self.furni[furni_id]["state"] = clock.half_seconds // 2

    def _clock_target(self, box: Box) -> int:
        seconds = _int(box.get("clock_minutes")) * 60 + _int(box.get("clock_seconds"))
        return seconds * 2 + (1 if box.get("clock_half") else 0)

    def _game_start(self) -> None:
        self.team_scores = dict.fromkeys(TEAMS, 0)
        self.score_grants.clear()
        self.game_running = True
        self._log("info", "Game started")
        self._fire("wf_trg_game_starts")

    def _game_end(self) -> None:
        if self.game_running:
            self.game_running = False
            self.game_timer = None
            for clock in self.clocks.values():
                if clock.game_aware:
                    clock.running = False
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
            elif action == "clock":
                self._clock_tick(payload["furni"], payload["run"])
            elif action == "game_timer":
                self._game_timer_tick(payload["furni"], payload["run"])
            elif action == "seat_turn_back":
                self._seat_users()
            elif action == "teleport":
                self._teleport_step(payload)
            elif action == "one_way_through":
                if payload["user"] in self.users:
                    self._move_user(payload["user"], payload["x"], payload["y"])
            elif action == "vend":
                self._vend_give(payload["user"], payload["furni"])
            elif action == "one_way_close":
                if payload["furni"] in self.furni:
                    self._set_state(payload["furni"], 0)
            elif action == "dice_land":
                if (
                    self.dice_turns.get(payload["furni"]) == payload["turn"]
                    and payload["furni"] in self.furni
                ):
                    self._set_state(payload["furni"], payload["face"])
            elif action == "sign_end":
                # A newer sign keeps its own time.
                if self.sign_turns.get(payload["user"]) == payload["turn"] and payload["user"] in self.users:
                    self.users[payload["user"]]["details"].pop("@sign", None)
            elif action == "signal":
                self._deliver_signal(payload["antennas"], payload["users"], payload["furni"])
            elif action == "link_message":
                self._deliver_message(payload["links"], payload["text"])
            elif action == "bot_step":
                if self.bot_turns.get(payload["bot"]) == payload["turn"]:
                    self._bot_step(payload["bot"])
            elif action == "bot_arrive":
                if payload["bot"] in self.users and payload["furni"] in self.furni:
                    target = self.furni[payload["furni"]]
                    self._move_bot(payload["bot"], target["x"], target["y"])
            elif action == "bot_effect_off":
                bot = self.users.get(payload["bot"])
                if bot is not None and bot["details"].get("@effect") == BOT_TELEPORT_EFFECT:
                    if payload["before"] is None:
                        bot["details"].pop("@effect", None)
                    else:
                        bot["details"]["@effect"] = payload["before"]

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
        self.last_context = context
        self.metrics[f"stack:{stack.key}"] += 1
        self.stack_work[stack.key] += len(stack.boxes)
        if context.trigger:
            self.box_runs[context.trigger.id] += 1
        label = self._name(context.trigger.classname) if context.trigger else "called"
        self._log("run", f"Stack {stack.key} runs, from {label}", stack=stack.key, user=context.user)
        self._flag_stubs(stack)
        self._apply_selectors(stack, context)
        passed = ignore_conditions or self._conditions_pass(stack, context)
        # Negative effects are the ones that run when the conditions fail, and only then.
        effects = [box for box in stack.of("effect") if box.classname.startswith(NEGATIVE) != passed]
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
        if (addon := stack.find("wf_xtra_random")) is not None:
            return self._random_effects(addon, known)
        if stack.find("wf_xtra_unseen"):
            if not stack.unseen:
                stack.unseen = [box.id for box in known]
                self.random.shuffle(stack.unseen)
            pick = stack.unseen.pop()
            return [box for box in known if box.id == pick]
        if stack.find("wf_xtra_exec_in_order"):
            # Bottom of the stack first. A real room set 3 then 9 from low to high and ended on 9.
            return sorted(known, key=lambda box: box.z)
        # Without Execute In Order the order is not guaranteed, so it varies here and exposes
        # stacks that rely on it by accident.
        shuffled = list(known)
        self.random.shuffle(shuffled)
        return shuffled

    def _random_effects(self, addon: Box, known: list[Box]) -> list[Box]:
        """Picks some effects, avoiding those its last few runs picked while others are left."""
        skip = max(0, min(_int(addon.get("skip", 0)), 100))
        pick = max(1, min(_int(addon.get("pick", 1), 1), 100))
        history = self.random_picks.setdefault(addon.id, deque())
        recent = {i for run in history for i in run}
        fresh = [box for box in known if box.id not in recent] or known
        chosen = self.random.sample(fresh, min(pick, len(fresh)))
        history.append([box.id for box in chosen])
        while len(history) > skip:
            history.popleft()
        return chosen

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
                    (u for u in ctx.users if self._holding(name, u, ctx, "user") is not None),
                    key=lambda u: self._holding(name, u, ctx, "user").value,  # type: ignore[union-attr]
                    reverse=not box.get("lowest"),
                )
                ctx.users = ranked[:amount]
            elif box.classname == "wf_xtra_filter_furni_by_var" and ctx.selected_furni is not None:
                name = str(box.get("variable", ""))
                ranked = sorted(
                    (i for i in ctx.selected_furni if self._holding(name, i, ctx, "furni") is not None),
                    key=lambda i: self._holding(name, i, ctx, "furni").value,  # type: ignore[union-attr]
                    reverse=not box.get("lowest"),
                )
                ctx.selected_furni = ranked[:amount]

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

    def _neighbourhood(self, box: Box, ctx: Context) -> set[tuple[int, int]]:
        """The tiles of a neighbourhood selector's drawing, around each of its users or furni."""
        if box.get("around", "users") == "furni":
            centres = [
                (self.furni[i]["x"], self.furni[i]["y"]) for i in self._furni_for(box, ctx) if i in self.furni
            ]
        else:
            centres = [
                (self.users[u]["x"], self.users[u]["y"]) for u in self._users_for(box, ctx) if u in self.users
            ]
        mask = box.get("mask")
        if not (isinstance(mask, list) and all(isinstance(n, int) for n in mask)):
            mask = neighbourhood.square_mask(_int(box.get("radius", 2), 2))
        root = (_int(box.get("root_x")), _int(box.get("root_y")))
        shape = neighbourhood.offsets(mask)
        return {(x + dx - root[0], y + dy - root[1]) for x, y in centres for dx, dy in shape}

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

    def _holds(self, name: str, on: str, holder: int, ctx: Context) -> bool:
        if internal.targets(name):
            return self._holding(name, holder, ctx, on) is not None
        return f"{on}:{holder}" in self.variables[name]

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
                return [i for i in self.furni if self._holds(name, "furni", i, ctx)]
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
                return [u for u in self.users if self._holds(name, "user", u, ctx)]
            case "wf_slc_users_area":
                return [u for u, d in self.users.items() if self._in_area(box, d["x"], d["y"])]
            case "wf_slc_users_onfurni":
                tiles = {
                    (self.furni[i]["x"], self.furni[i]["y"])
                    for i in _ids(box.get("furni"))
                    if i in self.furni
                }
                return [u for u, d in self.users.items() if (d["x"], d["y"]) in tiles]
            case "wf_slc_users_bytype":
                # A sandbox has Habbos and bots, but no pets.
                kinds = str(box.get("types", "habbo"))
                habbos, bots = kinds == "all" or "habbo" in kinds, kinds == "all" or "bot" in kinds
                return [u for u, d in self.users.items() if (bots if d.get("bot") else habbos)]
            case "wf_slc_users_handitem":
                hand = _int(box.get("handitem", 2), 2)
                return [u for u, d in self.users.items() if _int(d["details"].get("@handitem")) == hand]
            case "wf_slc_users_byaction":
                action = str(box.get("action", "wave"))
                return [u for u in self.users if self._performing(u, action, box)]
            case "wf_slc_users_neighborhood":
                tiles = self._neighbourhood(box, ctx)
                return [u for u, d in self.users.items() if (d["x"], d["y"]) in tiles]
            case "wf_slc_furni_neighborhood":
                tiles = self._neighbourhood(box, ctx)
                return [i for i, f in self.furni.items() if (f["x"], f["y"]) in tiles]
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
        return self._furni_from(box, ctx, "furni_source", "furni")

    def _furni_from(self, box: Box, ctx: Context, source_field: str, picks_field: str) -> list[int]:
        source = box.get(source_field, "default")
        picks = [i for i in _ids(box.get(picks_field)) if i in self.furni]
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
        match self._scope(box, name):
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
        on = self._scope(box, name)
        match box.classname:
            case "wf_cnd_counter_time_matches":
                return all(
                    _three_way(
                        box.get("clock_compare", "less"), self.clocks[i].half_seconds, self._clock_target(box)
                    )
                    for i in picks
                    if i in self.clocks
                )
            case "wf_cnd_team_has_score":
                wanted = box.get("team", "own")
                teams = (
                    [self.users[u]["team"] for u in users if u in self.users] if wanted == "own" else [wanted]
                )
                points = _int(box.get("points"))
                compare = box.get("score_compare", "less")
                return bool(teams) and all(
                    t in TEAMS and _three_way(compare, self.team_scores[t], points) for t in teams
                )
            case "wf_cnd_actor_in_team":
                return bool(users) and all(self._in_team(u, box.get("team", "any")) for u in users)
            case "wf_cnd_not_in_team":
                return all(not self._in_team(u, box.get("team", "any")) for u in users)
            case "wf_cnd_var_age_match":
                return bool(holders) and all(
                    self._age_matches(box, self._holding(name, h, ctx, on)) for h in holders
                )
            case "wf_cnd_has_var":
                return bool(holders) and all(self._holding(name, h, ctx, on) is not None for h in holders)
            case "wf_cnd_neg_has_var":
                return all(self._holding(name, h, ctx, on) is None for h in holders)
            case "wf_cnd_var_val_match":
                return bool(users) and all(
                    self._compare(box, self._holding(name, h, ctx, on), h, ctx) for h in holders
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
            case "wf_cnd_has_handitem":
                hand = _int(box.get("handitem", 2), 2)
                return self._quantify(box, [self._hand_item(u) == hand for u in users])
            case "wf_cnd_not_has_handitem":
                hand = _int(box.get("handitem", 2), 2)
                return self._quantify(box, [self._hand_item(u) != hand for u in users])
            case "wf_cnd_user_performs_action":
                action = str(box.get("action", "wave"))
                return self._quantify(
                    box, [self._performing(u, action, box) for u in users if u in self.users]
                )
            case "wf_cnd_not_user_performs_action":
                action = str(box.get("action", "wave"))
                return self._quantify(
                    box, [not self._performing(u, action, box) for u in users if u in self.users]
                )
            case "wf_cnd_actor_dir":
                faces = {n for n in range(8) if box.get(f"dir_{n}")}
                if not faces:
                    return False  # A box with no direction ticked never holds.
                return self._quantify(box, [self.users[u]["dir"] in faces for u in users if u in self.users])
            case "wf_cnd_has_altitude":
                wanted = _hundredths(box.get("altitude", 0))
                compare = box.get("altitude_compare", "less")
                found = [i for i in self._furni_for(box, ctx) if i in self.furni]
                return self._quantify(
                    box, [_three_way(compare, _hundredths(self.furni[i]["z"]), wanted) for i in found]
                )
            case "wf_cnd_slc_quantity":
                if box.get("count", "furni") == "users":
                    count = len(self._condition_users(box, ctx))
                else:
                    count = len(self._condition_furni(box, ctx))
                return _three_way(box.get("quantity_compare", "less"), count, _int(box.get("amount", 5), 5))
            case "wf_cnd_team_has_rank":
                placement = _int(box.get("placement", "1"), 1)
                team = box.get("team", "own")
                if team in TEAMS:
                    return self._rank(team) == placement
                teams = [self.users[u]["team"] for u in users if u in self.users]
                return self._quantify(box, [t in TEAMS and self._rank(t) == placement for t in teams])
            case "wf_cnd_match_date":
                return self._date_matches(box)
            case "wf_cnd_match_time":
                return self._time_matches(box)
            case "wf_cnd_date_rng_active":
                now = (self.clock_start_ms + self.now_ms) // 1000
                return _int(box.get("start", 0)) <= now <= _int(box.get("end", 0))
            case "wf_cnd_valid_moves":
                stack = self.stack_of.get(box.id)
                return stack is None or self._moves_valid(stack, ctx)
            case "wf_cnd_time_less_than":
                return self.now_ms - self.timer_start_ms < _int(box.get("seconds", 0)) * 1000
            case "wf_cnd_time_more_than":
                return self.now_ms - self.timer_start_ms > _int(box.get("seconds", 0)) * 1000
        return True

    @staticmethod
    def _quantify(box: Box, results: list[bool]) -> bool:
        """All or any of them, as the box says. With none at all, "all" holds and "any" does not."""
        return any(results) if box.get("quantifier", "all") == "any" else all(results)

    def _hand_item(self, user_id: int) -> int:
        user = self.users.get(user_id)
        return _int(user["details"].get("@handitem")) if user else 0

    def _condition_users(self, box: Box, ctx: Context) -> list[int]:
        source = box.get("user_source", "selector")
        if source == "trigger":
            return [ctx.user] if ctx.user is not None else []
        return list(ctx.signal_users) if source == "signal" else list(ctx.users or [])

    def _condition_furni(self, box: Box, ctx: Context) -> list[int]:
        source = box.get("furni_source", "selector")
        if source == "trigger":
            return [ctx.furni] if ctx.furni is not None else []
        return list(ctx.signal_furni) if source == "signal" else list(ctx.selected_furni or [])

    def _rank(self, team: str) -> int:
        """1 for the highest score. Teams on the same score share a place."""
        return 1 + sum(self.team_scores[other] > self.team_scores[team] for other in TEAMS)

    def _local_now(self) -> datetime:
        return datetime.fromtimestamp((self.clock_start_ms + self.now_ms) / 1000, tz=self.timezone)

    def _date_matches(self, box: Box) -> bool:
        """No weekday or month ticked counts as all of them. A day range past the month end wraps round."""
        now = self._local_now()
        weekdays = {n for n in range(7) if box.get(f"weekday_{n}", True)}
        if weekdays and now.weekday() not in weekdays:
            return False
        months = {n for n in range(12) if box.get(f"month_{n}", True)}
        if months and now.month - 1 not in months:
            return False
        if box.get("use_days") and not _in_range(
            now.day, _int(box.get("day_min", 1), 1), _int(box.get("day_max", 1), 1)
        ):
            return False
        return not (
            box.get("use_years")
            and not _int(box.get("year_min", 0)) <= now.year <= _int(box.get("year_max", 0))
        )

    def _time_matches(self, box: Box) -> bool:
        """Both ends count, and a range whose start is past its end wraps round: hours 22 to 2."""
        now = self._local_now()
        for unit, value in (("seconds", now.second), ("minutes", now.minute), ("hours", now.hour)):
            low, high = _int(box.get(f"{unit}_min", 0)), _int(box.get(f"{unit}_max", 0))
            if box.get(f"use_{unit}") and not _in_range(value, low, high):
                return False
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

    def _scope(self, box: Box, name: str) -> str:
        """The kind of holder a box means. A built-in name on both furni and users needs the box to say."""
        found = internal.targets(name)
        if not found:
            return str(self.definitions.get(name, {}).get("scope", "user"))
        chosen = box.get("variable_on", "user")
        return str(chosen) if chosen in found else found[0]

    def _built_in(self, name: str, on: str, holder: int | None, ctx: Context | None) -> Holding | None:
        """A built-in variable, worked out from the room. None if this holder has no such value."""
        row = internal.row_for(name, on)
        if row is None:
            return None
        value = self._built_in_value(name, row["target"], holder, ctx)
        if value is None:
            return None
        if not row["has_value"] and not value:
            return None  # A flag with no number exists only while it is true.
        return Holding(value, 0, 0)

    def _built_in_value(self, name: str, target: str, holder: int | None, ctx: Context | None) -> int | None:
        if target == "global":
            if name.startswith("@teams."):
                _, team, field = name.split(".")
                size = sum(1 for u in self.users.values() if u["team"] == team)
                return self.team_scores[team] if field == "score" else size
            if name.startswith("@current_time"):
                return self._current_time(name)
            return {
                "@room_id": self.room_id or None,
                "@furni_count": len(self.furni),
                "@user_count": len(self.users),
                "@wired_timer": (self.now_ms - self.timer_start_ms) // CLOCK_TICK_MS,
            }.get(name)
        if target == "context":
            if ctx is None:
                return None
            if name.startswith("@event."):
                return ctx.event.get(name)
            return {
                "@selector_furni_count": len(ctx.selected_furni or []),
                "@selector_user_count": len(ctx.users or []),
                "@signal_furni_count": len(ctx.signal_furni),
                "@signal_user_count": len(ctx.signal_users),
            }.get(name)
        if target == "user":
            user = self.users.get(holder) if holder is not None else None
            if user is None:
                return None
            team = user["team"]
            if name in USER_DETAILS:
                row = internal.row_for(name, "user")
                # Most of these exist only while they apply, such as a sign being held.
                if name not in user["details"] and row and not row.get("always_available"):
                    return None
                value = _int(user["details"].get(name))
                # A real room holds a favourite group only while there is one.
                return None if name == "@favourite_group_id" and not value else value
            return {
                "@type": 4 if user.get("bot") else 1,
                "@user_id": user["id"],
                "@team.type": TEAM_TYPE_NUMBERS[user["team_type"]] if team in TEAMS else None,
                "@index": user["id"],
                "@position.x": user["x"],
                "@position.y": user["y"],
                "@direction": user["dir"],
                "@team.color": TEAMS.index(team) + 1 if team in TEAMS else 0,
                "@team.score": self.team_scores[team] if team in TEAMS else 0,
            }.get(name)
        item = self.furni.get(holder) if holder is not None else None
        if item is None or holder is None:
            return None
        if name.startswith("@projectile.animation."):
            return self.projectile_values.get(holder, {}).get(name.removeprefix("@projectile.animation."))
        clock = self.clocks.get(holder)
        if name == "~clock.pulse_count":
            return clock.half_seconds if clock else None
        if name == "~clock.is_game_aware":
            return int(clock.game_aware) if clock else None
        if name == "~clock.state":
            return None if clock is None else 1 if clock.running else 2 if clock.started else 0
        facts = self.furni_facts.get(item["classname"], {})
        if name in FURNI_FACTS:
            known = facts.get(FURNI_FACTS[name])
            return None if known is None else int(known)
        if name == "@height":
            return _hundredths(facts["height"]) if "height" in facts else None
        return {
            "@id": holder,
            "@state": _int(item["state"]),
            "@position.x": item["x"],
            "@position.y": item["y"],
            "@rotation": item["rot"],
            "@altitude": _hundredths(item["z"]),
            "@is_invisible": int(bool(self.furni_looks.get(holder, {}).get("invisible"))),
        }.get(name)

    def _current_time(self, name: str) -> int | None:
        """Unix milliseconds, and its parts in the room's time zone. Day and month numbers start at 1, as in a real room."""
        now_ms = self.clock_start_ms + self.now_ms
        moment = datetime.fromtimestamp(now_ms / 1000, tz=self.timezone)
        return {
            "@current_time": now_ms,
            "@current_time.milliseconds_of_seconds": now_ms % 1000,
            "@current_time.seconds_of_minute": moment.second,
            "@current_time.minute_of_hour": moment.minute,
            "@current_time.hour_of_day": moment.hour,
            "@current_time.day_of_week": moment.isoweekday(),
            "@current_time.day_of_month": moment.day,
            "@current_time.day_of_year": moment.timetuple().tm_yday,
            "@current_time.week_of_year": moment.isocalendar().week,
            "@current_time.month_of_year": moment.month,
            "@current_time.year": moment.year,
        }.get(name)

    def _write_built_in(self, name: str, on: str, holder: int | None, value: int) -> bool:
        """Changes a writable built-in variable. False if this one cannot be changed here."""
        if name.startswith("@teams."):
            _, team, _field = name.split(".")
            before = self.team_scores[team]
            self.team_scores[team] = max(0, value)
            self._score_changed(team, before, None)
            return True
        if on == "user":
            user = self.users.get(holder) if holder is not None else None
            if user is None:
                return False
            match name:
                case "@direction":
                    user["dir"] = value % 8
                    self._turn_back_later()
                case "@position.x":
                    self._move_user(user["id"], value, user["y"])
                case "@position.y":
                    self._move_user(user["id"], user["x"], value)
                case "@handitem" | "@habbicon":
                    user["details"][name] = value
                case "@team.score" if user["team"] in TEAMS:
                    before = self.team_scores[user["team"]]
                    self.team_scores[user["team"]] = max(0, value)
                    self._score_changed(user["team"], before, user["id"])
                case _:
                    return False
            return True
        item = self.furni.get(holder) if holder is not None else None
        if item is None or holder is None:
            return False
        match name:
            case "@state":
                self._set_state(holder, value)
            case "@position.x":
                item["x"] = value
            case "@position.y":
                item["y"] = value
            case "@rotation":
                item["rot"] = value % 8
                self._seat_users()
            case "@altitude":
                item["z"] = max(0, min(value, MAX_ALTITUDE)) / 100
            case "~clock.pulse_count" if holder in self.clocks:
                self.clocks[holder].half_seconds = max(0, value)
                self._clock_show(holder, self.clocks[holder])
            case _:
                return False
        return True

    def view_built_ins(self, target: str, holder: int | None) -> list[dict[str, Any]]:
        """Every built-in value this holder has right now, for the inspection panel."""
        rows = []
        for row in internal.rows():
            if row["target"] == target:
                ctx = self.last_context if target == "context" else None
                holding = self._built_in(row["name"], target, holder, ctx)
                if holding is not None:
                    rows.append(
                        {"name": row["name"], "value": str(holding.value), "can_write": row["can_write"]}
                    )
        return rows

    def _holding(
        self, name: str, user: int | None, ctx: Context | None = None, on: str | None = None
    ) -> Holding | None:
        found = internal.targets(name)
        if found:
            chosen = on if on in found else "user" if "user" in found else found[0]
            return self._built_in(name, chosen, user, ctx)
        if name in self.pointers:
            pointed = self._pointed(name, ctx)
            return self._holding(pointed, user, ctx, on) if pointed else None
        name = self.echoes.get(name, name)
        if self.definitions.get(name, {}).get("scope") == "context":
            return ctx.context_vars.get(name) if ctx else None
        return self.variables[name].get(self._key(name, user))

    def _write(self, name: str, user: int | None, holding: Holding, ctx: Context | None) -> None:
        if name in self.pointers:
            return  # A real room changed nothing when a box wrote through a pointer.
        name = self.echoes.get(name, name)
        if self.definitions.get(name, {}).get("scope") == "context" and ctx is not None:
            ctx.context_vars[name] = holding
            return
        self.variables[name][self._key(name, user)] = holding

    def _changed(
        self,
        name: str,
        holder: int | None,
        before: int = 0,
        after: int = 0,
        change: int = 1,
        origin: int = 0,
    ) -> None:
        name = self.echoes.get(name, name)
        source = next(
            (
                b.id
                for s in self.stacks
                for b in s.boxes
                if b.classname.startswith("wf_var_") and b.get("variable") == name
            ),
            0,
        )
        event = {
            "@event.variable_update.box_id": source,
            "@event.variable_update.change_type": change,
            "@event.variable_update.new_value": after,
            "@event.variable_update.change_origin": origin,
        }
        # A new variable has no old value, and a real room printed null for both of these.
        if change != CHANGE_CREATED:
            event["@event.variable_update.old_value"] = before
            event["@event.variable_update.difference"] = after - before
        for stack, box in self._triggers("wf_trg_var_changed"):
            if box.get("variable") == name:
                is_furni = self.definitions.get(name, {}).get("scope") == "furni"
                self._start(
                    stack,
                    Context(trigger=box, furni=holder, event=event)
                    if is_furni
                    else Context(trigger=box, user=holder, event=event),
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

    def _through_pointer(self, box: Box, name: str) -> bool:
        """A real room changed nothing when a box gave, changed or took a variable through a pointer."""
        if name in self.pointers:
            self._log("info", f"{name} is a pointer, so nothing changed", box=box.id)
            return True
        return False

    def _do_give_var(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        if self._through_pointer(box, name):
            return
        if not name:
            self._log("error", "Give Variable has no variable chosen", box=box.id)
            return
        if name in ADDABLE_DETAILS:
            for target in self._users_for(box, ctx):
                who = self.users.get(target)
                if who is None or (name in who["details"] and not box.get("overwrite")):
                    continue
                amount = self._operand(box, target, ctx)
                if amount is not None:
                    who["details"][name] = _clamp(amount)
            return
        if internal.targets(name):
            self._log("stub", f"Writing to {name} is not simulated yet", box=box.id)
            return
        for user in self._holders(box, name, ctx):
            if self._holding(name, user, ctx) is not None and not box.get("overwrite"):
                continue
            amount = self._operand(box, user, ctx)
            if amount is None:
                continue
            self._write(name, user, Holding(_clamp(amount), self.now_ms, self.now_ms), ctx)
            self._changed(name, user, 0, _clamp(amount), CHANGE_CREATED)

    def _do_remove_var(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        if self._through_pointer(box, name):
            return
        if name in ADDABLE_DETAILS:
            for target in self._users_for(box, ctx):
                if (who := self.users.get(target)) is not None:
                    who["details"].pop(name, None)
            return
        if internal.targets(name):
            self._log("stub", f"Writing to {name} is not simulated yet", box=box.id)
            return
        for user in self._holders(box, name, ctx):
            if self.definitions.get(name, {}).get("scope") == "context":
                ctx.context_vars.pop(name, None)
            else:
                gone = self.variables[name].pop(self._key(name, user), None)
                self._changed(name, user, gone.value if gone else 0, 0, CHANGE_DELETED)
                continue
            self._changed(name, user, 0, 0, CHANGE_DELETED)

    def _operand(self, box: Box, user: int | None, ctx: Context) -> int | None:
        """The box's value, or what another variable holds for the same holder. None if it holds nothing."""
        reference = str(box.get("from_variable", "")).strip()
        if not reference:
            return _int(box.get("value", 0))
        source = self._holding(reference, user, ctx, self._scope(box, str(box.get("variable", ""))))
        if source is None:
            self._log(
                "error", f"{reference} is not set for {self._holder_label(reference, user)}", box=box.id
            )
            return None
        return self._read(source, str(box.get("from_field", "value")))

    def _change_built_in(self, box: Box, name: str, ctx: Context) -> None:
        on = self._scope(box, name)
        row = internal.row_for(name, on)
        for holder in self._holders(box, name, ctx):
            holding = self._holding(name, holder, ctx, on)
            amount = self._operand(box, holder, ctx)
            if row is None or not row["can_write"]:
                self._log("error", f"{name} cannot be changed", box=box.id)
                return
            if holding is None or amount is None:
                continue
            value = operations.apply(str(box.get("operation", "set")), holding.value, amount, self.random)
            if not self._write_built_in(name, on, holder, _clamp(value)):
                self._log("stub", f"Changing {name} is not simulated yet", box=box.id)

    def _do_change_var_val(self, box: Box, ctx: Context) -> None:
        name = str(box.get("variable", "")).strip()
        if self._through_pointer(box, name):
            return
        if internal.targets(name):
            self._change_built_in(box, name, ctx)
            return
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
            before = holding.value
            holding.value = _clamp(value)
            holding.updated_ms = self.now_ms
            self._changed(name, user, before, holding.value, CHANGE_VALUE)

    def _send(self, box: Box, ctx: Context) -> None:
        """A real room forwards the selected users unless told otherwise, all in one signal unless split."""
        antennas = _ids(box.get("antenna", []))
        source = box.get("user_source", "default")
        users = list(ctx.users or []) if source == "default" else self._users_for(box, ctx)
        furni = self._furni_for(box, ctx) if "furni" in box.settings else list(ctx.selected_furni or [])
        groups = [[user] for user in users] if box.get("split_users") and users else [users]
        for group in groups:
            self._push(self.now_ms, "signal", {"antennas": antennas, "users": group, "furni": furni})

    _do_send_signal = _send
    _do_neg_send_signal = _send

    def _do_send_message(self, box: Box, ctx: Context) -> None:
        """Sends the trigger's text, or the box's own message, through the chosen WIRED Links."""
        links = [i for i in self._furni_for(box, ctx) if self.furni[i]["classname"] == LINK]
        if not links:
            self._log("error", "Send Link Message has no WIRED Link chosen", box=box.id)
            return
        if box.get("message_source", "trigger") == "custom":
            message = self._text(box, ctx, ctx.user)
        else:
            message = ctx.text if ctx.text is not None else "null"  # What a real room sent without one.
        message = message.encode()[:LINK_MESSAGE_BYTES].decode(errors="ignore")
        if message:
            self._push(self.now_ms, "link_message", {"links": links, "text": message})

    def _deliver_message(self, links: list[int], text: str) -> None:
        """One room only: a Receive Link Message hears a message sent through a link it also chose."""
        self._log("signal", f"Link message through {links}: {text}")
        for stack, box in self._triggers("wf_trg_receive_message"):
            if set(_ids(box.get("furni", []))) & set(links):
                self._start(stack, Context(trigger=box, text=text))

    def _deliver_signal(self, antennas: list[int], users: list[int], furni: list[int]) -> None:
        self.metrics["signals"] += 1
        self._log("signal", f"Signal to antennas {antennas}", users=users)
        for stack, box in self._triggers("wf_trg_recv_signal"):
            if set(_ids(box.get("antenna", []))) & set(antennas):
                hits = sorted(set(_ids(box.get("antenna", []))) & set(antennas))
                self._start(
                    stack,
                    Context(
                        trigger=box,
                        signal_users=list(users),
                        signal_furni=list(furni),
                        event={"@event.signal.antenna_id": hits[0]},
                    ),
                )

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
        back = box.get("toggle_type", "next") == "previous"
        for furni_id in self._furni_for(box, ctx):
            if self.furni[furni_id]["classname"] not in NOT_WIRED_TOGGLED:
                self._set_state(
                    furni_id, self._previous_state(furni_id) if back else self._next_state(furni_id)
                )

    def _previous_state(self, furni_id: int) -> int:
        states = self._states(furni_id)
        current = self.furni[furni_id]["state"]
        return states[(states.index(current) - 1) % len(states)] if current in states else states[0]

    def _do_toggle_to_rnd(self, box: Box, ctx: Context) -> None:
        for furni_id in self._furni_for(box, ctx):
            self._set_state(furni_id, self.random.choice(self._states(furni_id)))

    def _text(self, box: Box, ctx: Context, user: int | None) -> str:
        values: dict[str, str] = {}
        if ctx.text is not None:
            values["trigger_text"] = ctx.text
        stack = self.stack_of.get(box.id)
        for addon in stack.of("addon") if stack else []:
            if addon.classname == "wf_xtra_text_output_username":
                values[str(addon.get("placeholder", "user"))] = self._user_name(user)
            elif addon.classname == "wf_xtra_text_output_furni_name":
                if addon.get("furni_source", "default") == "default":
                    named = [ctx.furni] if ctx.furni is not None else []
                else:
                    named = self._furni_for(addon, ctx)
                names = [self._furni_name(i) for i in named if i in self.furni]
                if addon.get("type", "single") == "single":
                    names = names[:1]
                values[str(addon.get("placeholder", "name"))] = ",".join(names)
            elif addon.classname == "wf_xtra_text_output_variable":
                name = str(addon.get("variable", ""))
                on = self._scope(addon, name)
                textual = addon.get("display", "numeric") == "textual"
                key = str(addon.get("placeholder", name))
                if addon.get("placeholder_type", "single") == "multiple":
                    # Every selected holder, or the triggering one, joined by the delimiter.
                    holders: list[int | None]
                    if on == "furni":
                        holders = list(ctx.selected_furni or []) or (
                            [ctx.furni] if ctx.furni is not None else []
                        )
                    elif on == "user":
                        holders = list(ctx.users or []) or ([user] if user is not None else [])
                    else:
                        holders = [None]
                    shown_all = [
                        self._shown(stack, name, self._holding(name, h, ctx, on), textual) or "null"
                        for h in holders
                    ]
                    values[key] = str(addon.get("delimiter", "")).join(shown_all)
                    continue
                holding = self._holding(name, ctx.furni if on == "furni" else user, ctx, on)
                shown = self._shown(stack, name, holding, textual)
                absent = holding is None and internal.targets(name)
                values[key] = "null" if absent else shown
        return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), str(box.get("text", "")))

    def _furni_name(self, furni_id: int) -> str:
        """The furni's public name, as Habbo shows it, or its class name when the catalogue has none."""
        classname = self.furni[furni_id]["classname"]
        return str(self.furni_facts.get(classname, {}).get("name") or classname)

    def _shown(self, stack: Stack | None, name: str, holding: Holding | None, textual: bool) -> str:
        """Numeric shows the number. Textual shows a Text Connector's label for it, or the number."""
        if holding is None:
            return ""
        return self._connected(stack, name, holding) if textual else str(holding.value)

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
                if user in self.thaw_on_teleport:
                    self._unfreeze(user)

    _do_teleport_to = _teleport

    def _do_user_to_furni(self, box: Box, ctx: Context) -> None:
        """A real room walks nobody onto furni they cannot stand on, and it moved them onto a tile."""
        known = [i for i in _ids(box.get("furni")) if i in self.furni]
        if all(self.furni[i]["classname"] not in self.not_standable for i in known):
            self._teleport(box, ctx)

    def _in_team(self, user_id: int, team: Any) -> bool:
        user = self.users.get(user_id)
        if not user or user["team"] is None:
            return False
        return bool(team == "any" or user["team"] == team)

    def _look_targets(self, box: Box, ctx: Context) -> tuple[dict[int, dict[str, Any]], list[int]] | None:
        """Where a look goes, or None if nobody is there to see it."""
        if box.get("audience", "selected") != "everyone" and not self._users_for(box, ctx):
            return None
        if box.get("target", "furni") == "users":
            # The box's first user source is its audience. The target falls back to the triggering user.
            target = [ctx.user] if ctx.user in self.users else []
            return self.user_looks, [u for u in target if u is not None]
        return self.furni_looks, self._furni_for(box, ctx)

    def _do_set_highlight(self, box: Box, ctx: Context) -> None:
        found = self._look_targets(box, ctx)
        if found:
            looks, targets = found
            for target in targets:
                looks.setdefault(target, {})["highlight"] = {
                    "type": str(box.get("highlight_type", "outline")),
                    "strength": max(0, min(_int(box.get("strength", 100), 100), 100)),
                    "color": max(0, min(_int(box.get("color", 16771584), 16771584), 0xFFFFFF)),
                    "pulse": bool(box.get("pulse")),
                    "easing": max(0, min(_int(box.get("easing", 4), 4), 4)),
                    "since_ms": self.now_ms,
                }

    def _do_set_visibility(self, box: Box, ctx: Context) -> None:
        found = self._look_targets(box, ctx)
        if found:
            looks, targets = found
            for target in targets:
                look = looks.setdefault(target, {})
                look["invisible"] = box.get("visibility", "invisible") != "visible"
                look["click_through"] = bool(box.get("click_through"))
                look["fade"] = {
                    "easing": max(0, min(_int(box.get("easing", 4), 4), 4)),
                    "since_ms": self.now_ms,
                }

    def _do_control_clock(self, box: Box, ctx: Context) -> None:
        command = box.get("clock_control", "start")
        for furni_id in self._furni_for(box, ctx):
            clock = self.clocks.get(furni_id)
            if clock is None:
                continue
            match command:
                case "start":
                    if clock.running:
                        clock.running, clock.stopped = False, True
                        if clock.game_aware:
                            self._game_end()
                    if clock.stopped:
                        clock.half_seconds = 0
                        self._clock_show(furni_id, clock)
                    self._clock_run(furni_id, clock)
                case "stop":
                    was_running = clock.running
                    clock.running, clock.stopped = False, True
                    if was_running and clock.game_aware:
                        self._game_end()
                case "reset" if clock.started:
                    clock.running, clock.started, clock.stopped = False, False, False
                    clock.half_seconds = 0
                    self._clock_show(furni_id, clock)
                case "pause":
                    clock.running = False
                case "resume":
                    self._clock_run(furni_id, clock)

    def _do_adjust_clock(self, box: Box, ctx: Context) -> None:
        amount = self._clock_target(box)
        change = box.get("clock_change", "add")
        for furni_id in self._furni_for(box, ctx):
            clock = self.clocks.get(furni_id)
            if clock is not None:
                current = clock.half_seconds
                wanted = (
                    amount
                    if change == "set"
                    else current - amount
                    if change == "subtract"
                    else current + amount
                )
                clock.half_seconds = max(0, wanted)
                self._clock_show(furni_id, clock)

    def _do_join_team(self, box: Box, ctx: Context) -> None:
        team = box.get("team", "red")
        if team in TEAMS:
            for user_id in self._users_for(box, ctx):
                if user_id in self.users:
                    self.users[user_id]["team"] = team
                    kind = box.get("team_type", "wired")
                    self.users[user_id]["team_type"] = kind if kind in TEAM_TYPES else "wired"
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
        before = self.team_scores[team]
        self.team_scores[team] = max(0, self.team_scores[team] + points)
        self._score_changed(team, before, scorer)
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

    def _carried(self, box: Box | None, ctx: Context | None, furni_id: int, x: int, y: int) -> list[int]:
        """The users a stack's Carry Users add-on takes along from a tile."""
        stack = self.stack_of.get(box.id) if box else None
        addon = stack.find("wf_xtra_mov_carry_users") if stack else None
        if addon is None or ctx is None:
            return []
        here = [u for u, d in self.users.items() if (d["x"], d["y"]) == (x, y)]
        if addon.get("carry", "furni") == "furni":
            # Only those standing on this furni itself, not on others on its tile.
            top = self._top_furni(x, y)
            if top is None or top["id"] != furni_id:
                return []
        if addon.get("user_source", "default") == "default":
            return here
        allowed = self._users_for(addon, ctx)
        return [u for u in here if u in allowed]

    def _shift_furni(
        self, furni_id: int, dx: int, dy: int, box: Box | None = None, ctx: Context | None = None
    ) -> bool:
        """A move off the room or onto a user cannot be made, and the furni stays put.

        Movement Physics changes that: the move may go through users, and furni on the tile decide too.
        """
        item = self.furni[furni_id]
        x, y = item["x"] + dx, item["y"] + dy
        if self._blocked(furni_id, x, y, box, ctx):
            return False
        carried = self._carried(box, ctx, furni_id, item["x"], item["y"])
        self._place(box, ctx, furni_id, x, y)
        for user in carried:
            self._move_user(user, x, y)
        return True

    def _blocked(self, furni_id: int, x: int, y: int, box: Box | None, ctx: Context | None) -> bool:
        """Off the room, onto a user, or refused by furni under Movement Physics."""
        if self._off_map(x, y):
            return True
        physics = self._movement(box, ctx)["physics"]
        here = {u for u, d in self.users.items() if (d["x"], d["y"]) == (x, y)}
        if here and not self._through_users(physics, here):
            return True
        return physics is not None and self._furni_block(furni_id, x, y, physics)

    def _place(self, box: Box | None, ctx: Context | None, furni_id: int, x: int, y: int) -> None:
        """Moves a furni to a tile, as the stack's movement add-ons say it looks and lands."""
        physics = self._movement(box, ctx)["physics"]
        self._launch(box, ctx, furni_id, x, y)
        item = self.furni[furni_id]
        item["x"], item["y"] = x, y
        if physics is not None and not physics.get("keep"):
            item["z"] = self._landing(furni_id, x, y)

    @staticmethod
    def _through_users(physics: dict[str, Any] | None, here: set[int]) -> bool:
        if physics is None or "through_users" not in physics:
            return False
        allowed = physics["through_users"]
        return allowed is None or here <= allowed

    def _furni_block(self, furni_id: int, x: int, y: int, physics: dict[str, Any]) -> bool:
        """With Movement Physics, a furni that cannot hold others refuses the move, as in a real room.

        Furni it may move through never refuse it. Furni it is blocked by always do, even stackable ones.
        """
        for other in self._covering(x, y):
            if other == furni_id:
                continue
            blocking = physics.get("blocked", False)
            if blocking is None or (blocking and other in blocking):
                return True
            through = physics.get("through_furni", False)
            if through is None or (through and other in through):
                continue
            classname = self.furni[other]["classname"]
            if not self.furni_facts.get(classname, {}).get("stackable", classname not in self.furni_facts):
                return True
        return False

    def _landing(self, furni_id: int, x: int, y: int) -> float:
        """Without Keep Altitude a moved furni lands on top of whatever is on its new tile."""
        tops = [
            self.furni[i]["z"] + self._height(self.furni[i]["classname"])
            for i in self._covering(x, y)
            if i != furni_id
        ]
        return max(tops, default=0.0)

    def _height(self, classname: str) -> float:
        known = self.heights.get(classname)
        if known is not None:
            return float(known)
        return _float(self.furni_facts.get(classname, {}).get("height"), 0.0)

    def _movement(self, box: Box | None, ctx: Context | None) -> dict[str, Any]:
        """What the stack's movement add-ons say: the move's time, whether it is instant, its curve and physics."""
        found: dict[str, Any] = {"ms": None, "instant": False, "curve": None, "physics": None}
        stack = self.stack_of.get(box.id) if box else None
        if stack is None or ctx is None:
            return found
        for addon in stack.of("addon"):
            match addon.classname:
                case "wf_xtra_mov_no_animation":
                    found["instant"] = True
                case "wf_xtra_anim_time":
                    ms = max(ANIM_MIN_MS, min(_int(addon.get("anim_ms", 500), 500), ANIM_MAX_MS))
                    # A second Animation Time adds to the first.
                    found["ms"] = (found["ms"] or 0) + ms
                case "wf_xtra_mov_curve":
                    strength = self._curve_strength(addon, ctx)
                    if strength is not None:
                        found["curve"] = strength
                case "wf_xtra_mov_physics":
                    found["physics"] = self._physics(addon, ctx, found["physics"])
        return found

    def _curve_strength(self, addon: Box, ctx: Context) -> int | None:
        """The curve's strength, or None when its variable is held by none of the chosen holders."""
        value = _int(addon.get("curve", 160), 160)
        if addon.get("curve_from_var"):
            name = str(addon.get("variable", "")).strip()
            on = str(addon.get("curve_on", "context"))
            holders: list[int | None]
            if on == "user":
                holders = list(self._users_for(addon, ctx))
            elif on == "furni":
                holders = list(self._furni_for(addon, ctx))
            else:
                holders = [None]
            held = next(
                (h for h in (self._holding(name, holder, ctx, on) for holder in holders) if h is not None),
                None,
            )
            if held is None:
                return None
            value = held.value
        return max(-CURVE_LIMIT, min(value, CURVE_LIMIT))

    def _physics(self, addon: Box, ctx: Context, had: dict[str, Any] | None) -> dict[str, Any]:
        """Two Movement Physics add up. A box that already set an option keeps its own furni or users."""
        physics = dict(had or {})
        if addon.get("keep_altitude", True):
            physics["keep"] = True
        if addon.get("through_furni") and "through_furni" not in physics:
            physics["through_furni"] = self._physics_furni(addon, ctx, "through")
        if addon.get("blocked_by_furni") and "blocked" not in physics:
            physics["blocked"] = self._physics_furni(addon, ctx, "blocking")
        if addon.get("through_users") and "through_users" not in physics:
            source = addon.get("user_source", "room")
            physics["through_users"] = None if source == "room" else set(self._users_for(addon, ctx))
        return physics

    def _physics_furni(self, addon: Box, ctx: Context, which: str) -> set[int] | None:
        """The furni one of Movement Physics' lists names. None means every furni in the room."""
        match addon.get(f"{which}_source", "room"):
            case "picks":
                return {i for i in _ids(addon.get(f"{which}_picks")) if i in self.furni}
            case "trigger":
                return {ctx.furni} if ctx.furni is not None else set()
            case "signal":
                return set(ctx.signal_furni)
            case "selector":
                return set(ctx.selected_furni or [])
        return None

    def _launch(self, box: Box | None, ctx: Context | None, furni_id: int, x: int, y: int) -> None:
        """What a stack's Projectile and animation add-ons do to a furni the stack is about to move."""
        stack = self.stack_of.get(box.id) if box else None
        addon = stack.find("wf_xtra_rotate_to_dir") if stack else None
        if addon is None or ctx is None:
            self._animate(box, ctx, furni_id, x, y)
            return
        if addon.get("furni_source", "default") != "default" and furni_id not in self._furni_for(addon, ctx):
            return
        item = self.furni[furni_id]
        dx, dy = x - item["x"], y - item["y"]
        if not dx and not dy:
            return
        facing = round(math.atan2(dx, -dy) / (math.pi / 4)) % 8
        if addon.get("proj_rotate", True):
            item["rot"] = (facing + _int(addon.get("proj_offset"))) % 8
            self._seat_users()
        if addon.get("proj_shooter", True):
            for user in self._users_for(addon, ctx):
                if user in self.users:
                    self.users[user]["dir"] = facing
            self._turn_back_later()
        tiles = max(abs(dx), abs(dy))
        if _int(addon.get("proj_variables")):
            self.projectile_values[furni_id] = {
                "tiles_travelled": tiles,
                "user_collisions": 0,
                "furni_collisions": 0,
                "position.x": x,
                "position.y": y,
                "position.altitude": _hundredths(item["z"]),
                "is_travelling": 0,
            }
        moves = self._movement(box, ctx)
        custom = addon.get("proj_custom_time", False)
        ms = (
            min(tiles * _int(addon.get("proj_tile_ms", 100), 100), MAX_FLIGHT_MS)
            if custom
            else moves["ms"] or DEFAULT_FLIGHT_MS
        )
        # Animation Curve overrides a projectile's own height; No Animation makes it land at once.
        height = moves["curve"] if moves["curve"] is not None else _int(addon.get("proj_height", 50), 50)
        self.flights.append(
            {
                "id": furni_id,
                "start_ms": self.now_ms,
                "ms": 1 if moves["instant"] else max(1, ms),
                "from": [item["x"], item["y"]],
                "to": [x, y],
                "height": height,
                "past": _int(addon.get("proj_past", 1), 1) if addon.get("proj_past_on") else 0,
            }
        )

    def _animate(self, box: Box | None, ctx: Context | None, furni_id: int, x: int, y: int) -> None:
        """No Animation, Animation Time and Animation Curve change how a plain move looks."""
        moves = self._movement(box, ctx)
        if not moves["instant"] and moves["ms"] is None and not moves["curve"]:
            return  # The browser slides it in the usual half second.
        item = self.furni[furni_id]
        if (item["x"], item["y"]) == (x, y):
            return
        self.flights.append(
            {
                "id": furni_id,
                "start_ms": self.now_ms,
                "ms": 1 if moves["instant"] else min(moves["ms"] or DEFAULT_FLIGHT_MS, MAX_FLIGHT_MS),
                "from": [item["x"], item["y"]],
                "to": [x, y],
                "height": moves["curve"] or 0,
                "past": 0,
            }
        )

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
            if (dx or dy) and not self._shift_furni(furni_id, dx, dy, box, ctx):
                continue
            rotation = str(box.get("rotation", "none"))
            turn = {"clockwise": 2, "counterclockwise": -2}.get(rotation, 0)
            if rotation == "random":
                turn = self.random.choice((0, 2, 4, 6))
            item["rot"] = (item["rot"] + turn) % 8
        self._seat_users()

    def _nearest_in_line(self, x: int, y: int) -> tuple[int, int] | None:
        """The nearest user on a furni's row or column within reach, with the distance."""
        found = [
            (abs(u["x"] - x) + abs(u["y"] - y), u["id"])
            for u in self.users.values()
            if (u["x"] == x or u["y"] == y) and abs(u["x"] - x) + abs(u["y"] - y) <= NOTICE_RANGE
        ]
        if not found:
            return None
        closest = min(d for d, _ in found)
        user = self.random.choice(sorted(u for d, u in found if d == closest))
        return user, closest

    def _collide(self, furni_id: int, user_id: int) -> None:
        self._fire("wf_trg_collision", user=user_id, furni=furni_id)

    def _try_steps(self, furni_id: int, steps: list[tuple[int, int]], box: Box, ctx: Context) -> bool:
        return any(self._shift_furni(furni_id, dx, dy, box, ctx) for dx, dy in steps)

    def _do_chase(self, box: Box, ctx: Context) -> None:
        """Steps toward the nearest user in line, or at random. Next to them it waits and collides."""
        hits: list[tuple[int, int]] = []
        for furni_id in self._furni_for(box, ctx):
            item = self.furni[furni_id]
            nearest = self._nearest_in_line(item["x"], item["y"])
            steps: list[tuple[int, int]] = []
            if nearest is not None:
                user, distance = nearest
                if distance <= 1:
                    hits.append((furni_id, user))
                    continue
                target = self.users[user]
                steps.append((_sign(target["x"] - item["x"]), _sign(target["y"] - item["y"])))
            steps += self.random.sample(CARDINAL_STEPS, len(CARDINAL_STEPS))
            self._try_steps(furni_id, steps, box, ctx)
        for furni_id, user in hits:
            self._collide(furni_id, user)
        self._seat_users()

    def _do_flee(self, box: Box, ctx: Context) -> None:
        """Steps away from the nearest user in line, else keeps its way. Next to a user it collides."""
        hits: list[tuple[int, int]] = []
        for furni_id in self._furni_for(box, ctx):
            item = self.furni[furni_id]
            nearest = self._nearest_in_line(item["x"], item["y"])
            key = (box.id, furni_id)
            if nearest is not None:
                user, distance = nearest
                if distance <= 1:
                    hits.append((furni_id, user))
                    continue
                target = self.users[user]
                away = (_sign(item["x"] - target["x"]), _sign(item["y"] - target["y"]))
                # Refused, it sidesteps a quarter clockwise, then the other way; never back.
                steps = [away, (-away[1], away[0]), (away[1], -away[0])]
            else:
                way = DIRECTION_STEPS[self.headings.get(key, 2)]
                sides = [(-way[1], way[0]), (way[1], -way[0])]
                steps = [way, *self.random.sample(sides, 2), (-way[0], -way[1])]
            for dx, dy in steps:
                if self._shift_furni(furni_id, dx, dy, box, ctx):
                    self.headings[key] = STEP_DIRECTIONS[(dx, dy)]
                    break
        for furni_id, user in hits:
            self._collide(furni_id, user)
        self._seat_users()

    def _do_move_to_dir(self, box: Box, ctx: Context) -> None:
        """Moves one tile the way the furni is heading, turning by the box's rule when blocked."""
        turn = str(box.get("turn", "wait"))
        block_users = box.get("block_users", True) is not False
        hits: list[tuple[int, int]] = []
        movers = self._furni_for(box, ctx)
        for furni_id in self.random.sample(movers, len(movers)):
            key = (box.id, furni_id)
            heading = self.headings.get(key, _int(box.get("start_dir", 0)) % 8)
            tried = 0
            for _ in range(8):
                item = self.furni[furni_id]
                tried |= 1 << heading
                dx, dy = DIRECTION_STEPS[heading]
                x, y = item["x"] + dx, item["y"] + dy
                users = [u["id"] for u in self.users.values() if (u["x"], u["y"]) == (x, y)]
                hits += [(furni_id, u) for u in users]
                if users and block_users:
                    break
                if not users and self._shift_furni(furni_id, dx, dy, box, ctx):
                    break
                if turn == "wait":
                    break
                heading = self._turned(heading, turn, tried)
            self.headings[key] = heading
        for furni_id, user in hits:
            self._collide(furni_id, user)
        self._seat_users()

    def _turned(self, heading: int, turn: str, tried: int) -> int:
        if turn == "random":
            untried = [d for d in range(8) if not tried & (1 << d)]
            return self.random.choice(untried) if untried else heading
        change = {"right_45": 1, "right_90": 2, "left_45": -1, "left_90": -2, "back": 4}.get(turn, 0)
        return (heading + change) % 8

    def _do_rel_mov(self, box: Box, ctx: Context) -> None:
        dx, dy = _int(box.get("move_x")), _int(box.get("move_y"))
        if dx or dy:
            for furni_id in self._furni_for(box, ctx):
                self._shift_furni(furni_id, dx, dy, box, ctx)

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
                self._place(box, ctx, furni_id, target["x"], target["y"])

    def _group_move(self, box: Box, ctx: Context) -> tuple[list[int], int, int] | None:
        """Move Furni as Group: the corner of the box round the group lands on the target plus the offset."""
        group = [i for i in self._furni_for(box, ctx) if i in self.furni]
        target: tuple[int, int] | None = None
        if box.get("target_user", True):
            users = [u for u in self._users_for(box, ctx) if u in self.users]
            if users:
                target = (self.users[users[0]]["x"], self.users[users[0]]["y"])
        else:
            found = self._furni_from(box, ctx, "target_source", "target_furni")
            if found:
                target = (self.furni[found[0]]["x"], self.furni[found[0]]["y"])
        if not group or target is None:
            return None
        dx = target[0] + _int(box.get("offset_x")) - min(self.furni[i]["x"] for i in group)
        dy = target[1] + _int(box.get("offset_y")) - min(self.furni[i]["y"] for i in group)
        return group, dx, dy

    def _do_move_furni_as_group(self, box: Box, ctx: Context) -> None:
        """Every furni moves by the same step. One that cannot go stays, and the rest still go."""
        planned = self._group_move(box, ctx)
        if planned is None or planned[1:] == (0, 0):
            return
        group, dx, dy = planned
        # The one furthest along goes first, so none is blocked by its own group; on a tile, the lowest.
        ahead = sorted(
            group,
            key=lambda i: (
                -(self.furni[i]["x"] * _sign(dx) + self.furni[i]["y"] * _sign(dy)),
                self.furni[i]["z"],
            ),
        )
        for furni_id in ahead:
            self._shift_furni(furni_id, dx, dy, box, ctx)
        self._seat_users()

    def _place_anchor(self, box: Box, ctx: Context) -> tuple[int, int, float] | None:
        """Where a custom Place Furni puts the first copy: a user's tile, or a furni's tile and altitude."""
        if box.get("target_user"):
            users = [u for u in self._users_for(box, ctx) if u in self.users]
            return (self.users[users[0]]["x"], self.users[users[0]]["y"], 0.0) if users else None
        found = self._furni_from(box, ctx, "target_source", "target_furni")
        if not found:
            return None
        target = self.furni[found[0]]
        return target["x"], target["y"], float(target["z"])

    def _do_place_furni(self, box: Box, ctx: Context) -> None:
        """Puts temporary copies of the picked furni in the room, as they were when the room started.

        A group keeps its layout: at a custom location the first copy lands on the target.
        """
        picks = [i for i in _ids(box.get("furni")) if i in self.templates and i in self.furni]
        sources = [self.templates[i] for i in picks if self.templates[i]["classname"] not in BOXES]
        if not sources:
            return
        anchor = None
        if box.get("location", "source") == "custom":
            anchor = self._place_anchor(box, ctx)
            if anchor is None:
                return
        first = sources[0]
        for template in sources:
            x, y = template["x"], template["y"]
            if anchor is not None:
                x, y = anchor[0] + x - first["x"], anchor[1] + y - first["y"]
            x, y = x + _int(box.get("offset_x")), y + _int(box.get("offset_y"))
            if self._off_map(x, y):
                self._log("info", "Place Furni cannot put a furni outside the room", box=box.id)
                continue
            match box.get("altitude", "top"):
                case "source":
                    z = float(template["z"])
                case "custom":
                    z = anchor[2] if anchor is not None else float(template["z"])
                case _:
                    z = self._landing(-1, x, y)
            z += _hundredths(box.get("offset_altitude", 0)) / 100
            copy = {**template, "id": self.next_furni_id, "x": x, "y": y, "temporary": True}
            copy["z"] = max(0, min(_hundredths(z), MAX_ALTITUDE)) / 100
            self.furni[self.next_furni_id] = copy
            self.next_furni_id += 1
        self._seat_users()

    def _do_remove_furni(self, box: Box, ctx: Context) -> None:
        """Takes out furni that Place Furni put there, and no others."""
        for furni_id in self._condition_furni(box, ctx):
            if self.furni.get(furni_id, {}).get("temporary"):
                del self.furni[furni_id]
                self.furni_looks.pop(furni_id, None)
                self.flights = [f for f in self.flights if f["id"] != furni_id]
        self._seat_users()

    def _frozen(self, user_id: int) -> bool:
        user = self.users.get(user_id)
        return bool(user and user["details"].get("@is_frozen"))

    def _do_freeze(self, box: Box, ctx: Context) -> None:
        effect = _int(box.get("effect", "218"), 218)
        for user_id in self._users_for(box, ctx):
            user = self.users.get(user_id)
            if user is None:
                continue
            if not self._frozen(user_id):
                self.before_freeze[user_id] = user["details"].get("@effect")
            user["details"]["@is_frozen"] = 1
            user["details"]["@effect"] = effect
            if box.get("thaw_on_teleport"):
                self.thaw_on_teleport.add(user_id)
            else:
                self.thaw_on_teleport.discard(user_id)

    def _do_unfreeze(self, box: Box, ctx: Context) -> None:
        for user_id in self._users_for(box, ctx):
            self._unfreeze(user_id)

    def _unfreeze(self, user_id: int) -> None:
        """The user walks again, and the effect worn before comes back unless another was put on since."""
        user = self.users.get(user_id)
        if user is None or not self._frozen(user_id):
            return
        user["details"].pop("@is_frozen", None)
        self.thaw_on_teleport.discard(user_id)
        before = self.before_freeze.pop(user_id, None)
        if user["details"].get("@effect") in FREEZE_EFFECTS:
            if before is None:
                user["details"].pop("@effect", None)
            else:
                user["details"]["@effect"] = before

    def _moves_valid(self, stack: Stack, ctx: Context) -> bool:
        """Can Perform Movements: every move the stack's effects would make, in a random order, can be made."""
        at = {i: (f["x"], f["y"]) for i, f in self.furni.items()}
        effects = [b for b in stack.of("effect") if b.spec is not None]
        for box in self.random.sample(effects, len(effects)):
            for furni_id, x, y in self._planned_moves(box, ctx, at):
                if self._blocked(furni_id, x, y, box, ctx):
                    return False
                at[furni_id] = (x, y)
        return True

    def _planned_moves(
        self, box: Box, ctx: Context, at: dict[int, tuple[int, int]]
    ) -> list[tuple[int, int, int]]:
        """Where an effect would move its furni. Random steps cannot be known ahead and are left out."""
        movers = [i for i in self._furni_for(box, ctx) if i in at]
        match box.classname:
            case "wf_act_rel_mov":
                dx, dy = _int(box.get("move_x")), _int(box.get("move_y"))
                return [(i, at[i][0] + dx, at[i][1] + dy) for i in movers if dx or dy]
            case "wf_act_move_rotate":
                direction = str(box.get("direction", "none"))
                if direction.startswith("random"):
                    return []
                dx, dy = self._furni_step(direction)
                return [(i, at[i][0] + dx, at[i][1] + dy) for i in movers if dx or dy]
            case "wf_act_move_to_dir":
                moves = []
                for i in movers:
                    heading = self.headings.get((box.id, i), _int(box.get("start_dir", "0")))
                    dx, dy = DIRECTION_STEPS[heading]
                    moves.append((i, at[i][0] + dx, at[i][1] + dy))
                return moves
            case "wf_act_furni_to_user":
                users = [u for u in self._users_for(box, ctx) if u in self.users]
                if not users:
                    return []
                target = self.users[users[0]]
                return [(i, target["x"], target["y"]) for i in movers]
            case "wf_act_move_furni_as_group":
                planned = self._group_move(box, ctx)
                if planned is None:
                    return []
                group, dx, dy = planned
                return [(i, at[i][0] + dx, at[i][1] + dy) for i in group if i in at and (dx or dy)]
        return []

    # --- Bots ---

    def _named_bots(self, name: str) -> list[int]:
        """Bots go by name, in any case. A space before or after a name is part of it."""
        if not name:
            return []
        return [u for u, d in self.users.items() if d.get("bot") and d["name"].lower() == name.lower()]

    def _bots_for(self, box: Box, ctx: Context, one: bool = False) -> list[int]:
        """The bot named in the box, or the bots among the triggering, selected or signal users.

        Follow, Give Hand Item and Talk to User act on one bot of the name; the others on all of them.
        """
        source = box.get("bot_source", "name")
        if source == "name":
            found = self._named_bots(str(box.get("bot_name", "")))
            return [self.random.choice(found)] if one and found else found
        if source == "trigger":
            users = [ctx.user] if ctx.user is not None else []
        elif source == "signal":
            users = list(ctx.signal_users)
        else:
            users = list(ctx.users or [])
        return [u for u in users if self.users.get(u, {}).get("bot")]

    def _walkable(self, x: int, y: int, goals: set[tuple[int, int]]) -> bool:
        if self._off_map(x, y) or self._someone_on(x, y):
            return False
        # A bot may end its walk on the furni it was sent to.
        return (x, y) in goals or all(
            self.furni[i]["classname"] not in self.not_standable for i in self._furni_on_tile(x, y)
        )

    def _path_step(self, bot: int, goals: set[tuple[int, int]]) -> tuple[int, int] | None:
        """The first step of a shortest walk to any goal tile, or None when none can be reached."""
        user = self.users[bot]
        start = (user["x"], user["y"])
        if start in goals:
            return None
        came: dict[tuple[int, int], tuple[int, int]] = {}
        queue = deque([start])
        seen = {start}
        while queue:
            here = queue.popleft()
            if here in goals:
                while came.get(here) != start:
                    here = came[here]
                return here
            if len(seen) > MAX_BOT_SEARCH:
                return None
            for dx, dy in DIRECTION_STEPS.values():
                step = (here[0] + dx, here[1] + dy)
                if step not in seen and self._walkable(*step, goals):
                    seen.add(step)
                    came[step] = here
                    queue.append(step)
        return None

    def _around(self, x: int, y: int) -> set[tuple[int, int]]:
        return {(x + dx, y + dy) for dx, dy in DIRECTION_STEPS.values()}

    def _schedule_bot(self, bot: int) -> None:
        self.bot_turns[bot] = self.bot_turns.get(bot, 0) + 1
        self._push(self.now_ms + BOT_STEP_MS, "bot_step", {"bot": bot, "turn": self.bot_turns[bot]})

    def _move_bot(self, bot: int, x: int, y: int) -> None:
        """A bot steps onto a tile. It fires Bot Reached Furni, not the user walk triggers."""
        user = self.users[bot]
        user["dir"] = STEP_DIRECTIONS.get((_sign(x - user["x"]), _sign(y - user["y"])), user["dir"])
        user["x"], user["y"] = x, y
        self._seat_users()
        for furni_id in self._furni_on_tile(x, y):
            for stack, box in self._triggers("wf_trg_bot_reached_stf"):
                picks = _ids(box.get("furni", []))
                if bot in self._named_bots(str(box.get("bot_name", ""))) and (not picks or furni_id in picks):
                    self._start(stack, Context(trigger=box, user=bot, furni=furni_id))

    def _bot_step(self, bot: int) -> None:
        if bot not in self.users:
            return
        follow = self.bot_follows.get(bot)
        if follow is not None:
            target = self.users.get(follow)
            if target is None:
                self.bot_follows.pop(bot, None)
                return
            me = self.users[bot]
            if interactions.next_to((me["x"], me["y"]), (target["x"], target["y"])):
                if not self.bot_caught.get(bot):
                    self.bot_caught[bot] = True
                    self._bot_reached_user(bot, follow)
            else:
                self.bot_caught[bot] = False
                step = self._path_step(bot, self._around(target["x"], target["y"]))
                if step is not None:
                    self._move_bot(bot, *step)
            self._schedule_bot(bot)
            return
        walk = self.bot_walks.get(bot)
        if walk is None:
            return
        step = self._path_step(bot, walk["goals"])
        me = self.users[bot]
        if step is not None:
            self._move_bot(bot, *step)
            if (me["x"], me["y"]) not in walk["goals"]:
                self._schedule_bot(bot)
                return
        self.bot_walks.pop(bot, None)
        if (me["x"], me["y"]) not in walk["goals"]:
            self._log("info", f"{me['name']} cannot get there")
            if walk.get("hand") is not None:
                me["details"].pop("@handitem", None)
            return
        if walk.get("hand") is not None:
            self._hand_over(bot, walk["user"], walk["hand"])

    def _bot_reached_user(self, bot: int, user: int) -> None:
        for stack, box in self._triggers("wf_trg_bot_reached_avtr"):
            if bot in self._named_bots(str(box.get("bot_name", ""))):
                self._start(stack, Context(trigger=box, user=user, users=[bot]))

    def _hand_over(self, bot: int, user: int, hand: int) -> None:
        self.users[bot]["details"].pop("@handitem", None)
        if user in self.users:
            self.users[user]["details"]["@handitem"] = hand
            self._log("info", f"{self.users[bot]['name']} gave {self.users[user]['name']} hand item {hand}")

    def _do_bot_move(self, box: Box, ctx: Context) -> None:
        """Each bot walks to one of the picked furni."""
        targets = [i for i in self._furni_for(box, ctx) if i in self.furni]
        if not targets:
            return
        for bot in self._bots_for(box, ctx):
            target = self.furni[self.random.choice(targets)]
            self.bot_follows.pop(bot, None)
            self.bot_walks[bot] = {"goals": {(target["x"], target["y"])}}
            self._schedule_bot(bot)

    def _do_bot_teleport(self, box: Box, ctx: Context) -> None:
        """A bot gets the teleport effect, appears on a picked furni 1.5 s later, and loses it at 3.1 s."""
        targets = [i for i in self._furni_for(box, ctx) if i in self.furni]
        if not targets:
            return
        for bot in self._bots_for(box, ctx):
            details = self.users[bot]["details"]
            before = details.get("@effect")
            details["@effect"] = BOT_TELEPORT_EFFECT
            self.bot_walks.pop(bot, None)
            self.bot_follows.pop(bot, None)
            self.bot_turns[bot] = self.bot_turns.get(bot, 0) + 1
            target = self.random.choice(targets)
            self._push(self.now_ms + BOT_ARRIVE_MS, "bot_arrive", {"bot": bot, "furni": target})
            self._push(self.now_ms + BOT_EFFECT_OFF_MS, "bot_effect_off", {"bot": bot, "before": before})

    def _do_bot_follow_avatar(self, box: Box, ctx: Context) -> None:
        users = [u for u in self._users_for(box, ctx) if u in self.users]
        for bot in self._bots_for(box, ctx, one=True):
            if box.get("follow", True) and users:
                self.bot_walks.pop(bot, None)
                self.bot_follows[bot] = users[0]
                self.bot_caught[bot] = False
                self._schedule_bot(bot)
            elif not box.get("follow", True):
                self.bot_follows.pop(bot, None)

    def _do_bot_give_handitem(self, box: Box, ctx: Context) -> None:
        """A bot carries the item to the first user and hands it over. With no bot, the users get it at once."""
        hand = _int(box.get("handitem", 2), 2)
        users = [u for u in self._users_for(box, ctx) if u in self.users]
        if not str(box.get("bot_name", "")) and box.get("bot_source", "name") == "name":
            for user in users:
                self.users[user]["details"]["@handitem"] = hand
            return
        bots = self._bots_for(box, ctx, one=True)
        if not bots or not users:
            return
        bot, user = bots[0], users[0]
        me, them = self.users[bot], self.users[user]
        if interactions.next_to((me["x"], me["y"]), (them["x"], them["y"])):
            self._hand_over(bot, user, hand)
            return
        me["details"]["@handitem"] = hand
        self.bot_follows.pop(bot, None)
        self.bot_walks[bot] = {"goals": self._around(them["x"], them["y"]), "user": user, "hand": hand}
        self._schedule_bot(bot)

    def _bot_says(self, bot: int, box: Box, text: str, to: int | None) -> None:
        name = self.users[bot]["name"]
        shown = text if box.get("hide_name") else f"{name}: {text}"
        self.messages.append({"at_ms": self.now_ms, "user": to, "speaker": bot, "text": shown})
        self._log("message", f"{name} {'whispers' if to is not None else 'says'}: {text}")

    def _do_bot_talk(self, box: Box, ctx: Context) -> None:
        text = self._text(box, ctx, ctx.user)
        for bot in self._bots_for(box, ctx):
            self._bot_says(bot, box, text, None)

    def _do_bot_talk_to_avatar(self, box: Box, ctx: Context) -> None:
        """Whispering, only the user hears it. Talking, the room hears it with the user's name first."""
        bots = self._bots_for(box, ctx, one=True)
        if not bots:
            return
        for user in self._users_for(box, ctx):
            if user not in self.users:
                continue
            text = self._text(box, ctx, user)
            if box.get("whisper"):
                self._bot_says(bots[0], box, text, user)
            else:
                self._bot_says(bots[0], box, f"{self.users[user]['name']}: {text}", None)

    def _do_bot_clothes(self, box: Box, ctx: Context) -> None:
        figure = str(box.get("figure", "")).strip()
        if not FIGURE.fullmatch(figure):
            self._log("error", "Bot Clothes has no valid figure", box=box.id)
            return
        for bot in self._bots_for(box, ctx):
            self.users[bot]["figure"] = figure

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
            self._shift_furni(furni_id, target["x"] - item["x"], target["y"] - item["y"], box, ctx)

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
        self._turn_back_later()

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

    def _view_flights(self) -> list[dict[str, Any]]:
        """Flights still in the air. Old ones are dropped, so a long run does not keep them all."""
        self.flights = [f for f in self.flights if f["start_ms"] + f["ms"] + 1000 > self.now_ms]
        return list(self.flights)

    def view_fx(self) -> list[dict[str, Any]]:
        """What each Variable FX box shows: the variable of the box on its tile, over everyone holding it."""
        shown = []
        for stack in self.stacks:
            source = next((b for b in stack.boxes if b.classname in ("wf_var_user", "wf_var_furni")), None)
            name = str(source.get("variable", "")).strip() if source else ""
            drawn = [b for b in stack.boxes if b.classname.startswith("wf_xtra_varfx_")]
            for box in drawn[:MAX_FX_PER_VARIABLE] if name else []:
                prefix = "furni" if box.get("fx_target", "user") == "furni" else "user"
                for key, holding in sorted(self.variables[name].items()):
                    holder, _, entity = key.partition(":")
                    if holder == prefix and self._fx_showing(box, holding):
                        shown.append(
                            {
                                "kind": box.classname.removeprefix("wf_xtra_varfx_"),
                                "target": prefix,
                                "id": _int(entity),
                                "value": str(holding.value),
                                "min": _int(box.get("fx_min")),
                                "max": _int(box.get("fx_max", 100), 100),
                                "order": _int(box.get("fx_order")),
                            }
                        )
        return shown

    def _fx_showing(self, box: Box, holding: Holding) -> bool:
        match box.get("fx_show", "always"):
            case "never":
                return False
            case "changes":
                return self.now_ms - holding.updated_ms < _int(box.get("fx_duration", 3000), 3000)
        return True

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

    def blocks_user_menu(self) -> bool:
        """A Click User box that says so keeps the avatar menu shut when someone is clicked."""
        return any(box.get("block_menu", True) for _, box in self._triggers("wf_trg_click_user"))

    def snapshot(self) -> dict[str, Any]:
        return {
            "now_ms": self.now_ms,
            "furni": sorted(
                (
                    {k: f[k] for k in ("id", "x", "y", "z", "rot", "state")}
                    # A copy Place Furni put there is not in the room's file, so the browser needs its kind.
                    | ({"classname": f["classname"], "temporary": True} if f.get("temporary") else {})
                    for f in self.furni.values()
                ),
                key=lambda f: f["id"],
            ),
            "users": sorted(self.users.values(), key=lambda u: u["id"]),
            "variables": self.view_variables(),
            "defined_variables": self.view_defined(),
            "fx": self.view_fx(),
            "flights": self._view_flights(),
            "looks": {"furni": self.furni_looks, "users": self.user_looks},
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
