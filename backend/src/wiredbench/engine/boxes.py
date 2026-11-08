"""What the engine knows about each WIRED box: its settings and how far its behaviour can be trusted.

Fidelity is deliberately plain. `documented` means a public source describes the behaviour, though details
may still differ. `assumed` means the behaviour is a best guess. Nothing is `verified` until it has been
compared with a real room. Boxes not listed here are placed as logging stubs.
"""

from __future__ import annotations

import re
from typing import Any

from wiredbench.engine.operations import OPERATION_LABELS

# Milliseconds in each unit a variable's age can be measured in. A month is 30 days and a year 365.
TIME_UNITS = {
    "milliseconds": 1,
    "seconds": 1000,
    "minutes": 60_000,
    "hours": 3_600_000,
    "days": 86_400_000,
    "weeks": 604_800_000,
    "months": 2_592_000_000,
    "years": 31_536_000_000,
}
DOCUMENTED = "documented"
ASSUMED = "assumed"
DEFAULT_DELAY = {
    "name": "delay",
    "kind": "number",
    "label": "Delay (half seconds, or negative milliseconds for precise delays)",
    "default": 0,
    "min": -60000,
    "max": 600,
}
FURNI = {"name": "furni", "kind": "furni", "label": "Furni", "default": []}
VARIABLE = {"name": "variable", "kind": "text", "label": "Variable name", "default": ""}
USER_SOURCE = {
    "name": "user_source",
    "kind": "select",
    "label": "Users from",
    "options": ["default", "trigger", "signal", "selector"],
    "default": "default",
}
FURNI_SOURCE = {
    "name": "furni_source",
    "kind": "select",
    "label": "Furni from",
    "options": ["default", "picks", "trigger", "signal", "selector"],
    "default": "default",
}
# The variable's kind decides which of these a box uses.
HOLDERS = [USER_SOURCE, FURNI, FURNI_SOURCE]
VARIABLE_ON = {
    "name": "variable_on",
    "kind": "select",
    "label": "A built-in variable on",
    "options": ["user", "furni"],
    "labels": {"user": "Users", "furni": "Furni"},
    "default": "user",
}
OVERWRITE = {"name": "overwrite", "kind": "bool", "label": "Overwrite if it already exists", "default": False}
VALUE = {"name": "value", "kind": "number", "label": "Value", "default": 0}
REFERENCE: list[dict[str, Any]] = [
    {
        "name": "from_variable",
        "kind": "text",
        "label": "Take the value from variable (optional)",
        "default": "",
    },
    {
        "name": "from_field",
        "kind": "select",
        "label": "Using its",
        "options": ["value", "creation", "update"],
        "default": "value",
    },
]
COMPARE = {
    "name": "compare",
    "kind": "select",
    "label": "Comparison",
    "options": ["=", "!=", ">", ">=", "<", "<="],
    "default": "=",
}
FILTER = {"name": "filter", "kind": "bool", "label": "Only narrow what is already selected", "default": False}
INVERT = {
    "name": "invert",
    "kind": "bool",
    "label": "Select everything that does not match",
    "default": False,
}
AREA = (
    {"name": "area_x", "kind": "number", "label": "Area starts at column", "default": 0, "min": 0},
    {"name": "area_y", "kind": "number", "label": "Area starts at row", "default": 0, "min": 0},
    {"name": "area_width", "kind": "number", "label": "Area width in tiles", "default": 0, "min": 0},
    {"name": "area_height", "kind": "number", "label": "Area height in tiles", "default": 0, "min": 0},
)
COMPASS = {
    "y-": "y - 1",
    "x+y-": "x + 1, y - 1",
    "x+": "x + 1",
    "x+y+": "x + 1, y + 1",
    "y+": "y + 1",
    "x-y+": "x - 1, y + 1",
    "x-": "x - 1",
    "x-y-": "x - 1, y - 1",
}
MOVERS = {
    **FURNI_SOURCE,
    "label": "Furni to move",
    "options": ["default", "trigger", "signal", "selector"],
}
TEAMS = ("red", "green", "blue", "yellow")
TEAM = {
    "name": "team",
    "kind": "select",
    "label": "Team",
    "options": list(TEAMS),
    "labels": {team: team.capitalize() for team in TEAMS},
    "default": "red",
}
ANY_TEAM = {
    **TEAM,
    "options": ["any", *TEAMS],
    "labels": {"any": "Any team", **{team: team.capitalize() for team in TEAMS}},
    "default": "any",
}
# What a user can be seen doing, with the number a real box saves for each. The labels are Habbo's own.
# Jump (67) is not in Habbo's list; it comes from a retro's notes and is unverified.
AVATAR_ACTIONS = {
    "wave": 0,
    "blow": 1,
    "laugh": 2,
    "respect": 3,
    "awake": 4,
    "sleep": 5,
    "sit": 6,
    "stand": 7,
    "lay": 8,
    "swim": 9,
    "sign": 10,
    "dance": 11,
    "jump": 67,
}
AVATAR_ACTION = {
    "name": "action",
    "kind": "select",
    "label": "Action",
    "options": list(AVATAR_ACTIONS),
    "labels": {
        "wave": "Wave",
        "blow": "Blow",
        "laugh": "Laugh",
        "respect": "Thumbs up",
        "awake": "Awake",
        "sleep": "Idle",
        "sit": "Sit",
        "stand": "Stand",
        "lay": "Lay",
        "swim": "Swim",
        "sign": "Sign",
        "dance": "Dance",
        "jump": "Jump (67, unverified)",
    },
    "default": "wave",
}
# For a sign or a dance, which one. Empty matches any.
ACTION_NUMBER = {
    "name": "text",
    "kind": "text",
    "label": "Which sign (0 to 17) or dance (1 to 4); empty for any",
    "default": "",
}
# The neighbourhood selectors pick what stands on tiles around users or furni. A real box stores a
# drawing of up to 21 by 21 tiles. Here a square is drawn by its size, and an imported drawing is kept.
NEIGHBOURHOOD = (
    {
        "name": "around",
        "kind": "select",
        "label": "In neighbourhood of",
        "options": ["users", "furni"],
        "labels": {"users": "Users", "furni": "Furni"},
        "default": "users",
    },
    USER_SOURCE,
    FURNI,
    FURNI_SOURCE,
    {
        "name": "radius",
        "kind": "number",
        "label": "Tiles out from the centre (a square; an imported drawing is kept until this changes)",
        "default": 2,
        "min": 0,
        "max": 10,
    },
    {
        "name": "root_x",
        "kind": "number",
        "label": "Move the centre by x",
        "default": 0,
        "min": -64,
        "max": 64,
    },
    {
        "name": "root_y",
        "kind": "number",
        "label": "Move the centre by y",
        "default": 0,
        "min": -64,
        "max": 64,
    },
)
POINTS = (
    {"name": "points", "kind": "number", "label": "Points", "default": 5, "min": -1000, "max": 1000},
    {
        "name": "times",
        "kind": "number",
        "label": "Times per game, 0 for no limit",
        "default": 0,
        "min": 0,
        "max": 10,
    },
)
CLOCK_TIME = (
    {"name": "clock_minutes", "kind": "number", "label": "Minutes", "default": 0, "min": 0, "max": 99},
    {"name": "clock_seconds", "kind": "number", "label": "Seconds", "default": 0, "min": 0, "max": 59},
    {"name": "clock_half", "kind": "bool", "label": "And half a second", "default": False},
)
THREE_WAY = {
    "kind": "select",
    "label": "Comparison",
    "options": ["less", "equal", "more"],
    "labels": {"less": "Less than", "equal": "Exactly", "more": "More than"},
    "default": "less",
}
AUDIENCE = {
    "name": "audience",
    "kind": "select",
    "label": "Who sees it",
    "options": ["selected", "everyone"],
    "labels": {"selected": "The users below", "everyone": "Everyone"},
    "default": "selected",
}
TARGET_KIND = {
    "name": "target",
    "kind": "select",
    "label": "Applies to",
    "options": ["furni", "users"],
    "labels": {"furni": "Furni", "users": "Users"},
    "default": "furni",
}
EASING = {"name": "easing", "kind": "number", "label": "Easing, 0 to 4", "default": 4, "min": 0, "max": 4}
FX_COMMON = (
    {
        "name": "fx_target",
        "kind": "select",
        "label": "Shows over",
        "options": ["user", "furni"],
        "labels": {"user": "Users", "furni": "Furni"},
        "default": "user",
    },
    {
        "name": "fx_show",
        "kind": "select",
        "label": "Show",
        "options": ["always", "changes", "never"],
        "labels": {"always": "Always", "changes": "When it changes", "never": "Never"},
        "default": "always",
    },
    {
        "name": "fx_duration",
        "kind": "number",
        "label": "Show for, in milliseconds",
        "default": 3000,
        "min": 1500,
        "max": 20000,
    },
    {"name": "fx_order", "kind": "number", "label": "Order, higher sits lower", "default": 0},
)
FX_RANGE = (
    {"name": "fx_min", "kind": "number", "label": "Lowest value", "default": 0},
    {"name": "fx_max", "kind": "number", "label": "Highest value", "default": 100},
)
SPLIT_USERS = {"name": "split_users", "kind": "bool", "label": "One signal per user", "default": False}
AMOUNT = {"name": "amount", "kind": "number", "label": "How many", "default": 10, "min": 0}
ANTENNA = {"name": "antenna", "kind": "furni", "label": "Antenna", "default": []}
LINKS = {"name": "furni", "kind": "furni", "label": "WIRED Links", "default": []}
PHYSICS_FURNI = {
    **FURNI_SOURCE,
    "options": ["room", "picks", "trigger", "signal", "selector"],
    "labels": {"room": "All furni in the room"},
    "default": "room",
}
# Animation Time keeps a value outside these at the nearest end; Curve's strength the same.
ANIM_MIN_MS, ANIM_MAX_MS = 50, 2000
CURVE_LIMIT = 1000
SECONDS = {"name": "seconds", "kind": "number", "label": "Seconds", "default": 10, "min": 0, "step": 0.5}


def _saved(field: dict[str, Any]) -> dict[str, Any]:
    """A real option that the engine does not act on yet. It is kept, and the form says so."""
    return {**field, "saved_only": True}


def _box(kind: str, fidelity: str, *fields: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "fidelity": fidelity, "fields": list(fields)}


def _selector(fidelity: str, *fields: dict[str, Any]) -> dict[str, Any]:
    return _box("selector", fidelity, *fields, FILTER, INVERT)


def _effect(fidelity: str, *fields: dict[str, Any]) -> dict[str, Any]:
    return _box("effect", fidelity, *fields, DEFAULT_DELAY)


AVAILABILITY_LABELS = {
    "active": "While in the room (not listed by the Web API)",
    "persistent": "Persistent",
    "shared": "Shared",
}


def _availability(*options: str) -> dict[str, Any]:
    return _saved(
        {
            "name": "availability",
            "kind": "select",
            "label": "Availability",
            "options": list(options),
            "labels": AVAILABILITY_LABELS,
            "default": "active",
        }
    )


HAS_VALUE = _saved({"name": "has_value", "kind": "bool", "label": "Has a number value", "default": False})
LOG_LEVEL = _saved(
    {"name": "level", "kind": "select", "label": "Log level", "options": ["0", "1", "2", "3"], "default": "0"}
)

BOXES: dict[str, dict[str, Any]] = {
    # Triggers
    "wf_trg_walks_on_furni": _box("trigger", DOCUMENTED, FURNI),
    "wf_trg_walks_off_furni": _box("trigger", DOCUMENTED, FURNI),
    "wf_trg_click_furni": _box("trigger", DOCUMENTED, FURNI),
    "wf_trg_state_changed": _box("trigger", DOCUMENTED, FURNI),
    "wf_trg_stuff_state": _box("trigger", DOCUMENTED, FURNI),
    "wf_trg_says_something": _box(
        "trigger",
        DOCUMENTED,
        {"name": "text", "kind": "text", "label": "What is said (not used by Match all text)", "default": ""},
        {
            "name": "match",
            "kind": "select",
            "label": "Choose type",
            "options": ["contains", "exact", "all"],
            "labels": {"contains": "Contains keyword", "exact": "Exact match", "all": "Match all text"},
            "default": "contains",
        },
        _saved(
            {"name": "hide_message", "kind": "bool", "label": "Hide the triggerer's message", "default": True}
        ),
        _saved(
            {
                "name": "owner_only",
                "kind": "bool",
                "label": "Only the room owner can trigger",
                "default": False,
            }
        ),
    ),
    "wf_trg_enter_room": _box("trigger", DOCUMENTED),
    "wf_trg_leave_room": _box("trigger", ASSUMED),
    "wf_trg_room_initializes": _box("trigger", ASSUMED),
    "wf_trg_periodically": _box("trigger", DOCUMENTED, {**SECONDS, "default": 0.5}),
    "wf_trg_period_short": _box("trigger", ASSUMED, {**SECONDS, "default": 0.2, "step": 0.05}),
    "wf_trg_period_long": _box("trigger", DOCUMENTED, {**SECONDS, "default": 50, "step": 5}),
    "wf_trg_at_given_time": _box("trigger", DOCUMENTED, SECONDS),
    "wf_trg_recv_signal": _box("trigger", DOCUMENTED, ANTENNA),
    "wf_trg_var_changed": _box("trigger", ASSUMED, VARIABLE),
    "wf_trg_collision": _box("trigger", DOCUMENTED),
    "wf_trg_receive_message": _box("trigger", ASSUMED, LINKS),
    "wf_trg_click_tile": _box("trigger", DOCUMENTED, {**FURNI, "label": "Invisible click tiles"}),
    "wf_trg_user_performs_action": _box("trigger", DOCUMENTED, AVATAR_ACTION, ACTION_NUMBER),
    "wf_trg_click_user": _box(
        "trigger",
        DOCUMENTED,
        _saved({"name": "block_menu", "kind": "bool", "label": "Do not open avatar menu", "default": True}),
        {"name": "keep_facing", "kind": "bool", "label": "Do not rotate", "default": False},
    ),
    "wf_trg_score_achieved": _box(
        "trigger",
        DOCUMENTED,
        {"name": "points", "kind": "number", "label": "Score reached", "default": 100, "min": 1, "max": 1000},
        ANY_TEAM,
    ),
    # Conditions
    "wf_cnd_var_age_match": _box(
        "condition",
        ASSUMED,
        VARIABLE,
        VARIABLE_ON,
        {
            "name": "compare",
            "kind": "select",
            "label": "Its age is",
            "options": ["less", "equal", "more"],
            "labels": {"less": "Less than", "equal": "Exactly", "more": "More than"},
            "default": "less",
        },
        {"name": "duration", "kind": "number", "label": "Amount", "default": 0, "min": 0},
        {
            "name": "unit",
            "kind": "select",
            "label": "Unit",
            "options": list(TIME_UNITS),
            "labels": {unit: unit.capitalize() for unit in TIME_UNITS},
            "default": "seconds",
        },
        {
            "name": "age_of",
            "kind": "select",
            "label": "Measured from",
            "options": ["creation", "update"],
            "labels": {"creation": "When it was given", "update": "When it last changed"},
            "default": "creation",
        },
        *HOLDERS,
    ),
    "wf_cnd_actor_in_team": _box("condition", ASSUMED, ANY_TEAM, USER_SOURCE),
    "wf_cnd_not_in_team": _box("condition", ASSUMED, ANY_TEAM, USER_SOURCE),
    "wf_cnd_counter_time_matches": _box(
        "condition", ASSUMED, FURNI, *CLOCK_TIME, {**THREE_WAY, "name": "clock_compare"}
    ),
    "wf_cnd_team_has_score": _box(
        "condition",
        ASSUMED,
        {
            **TEAM,
            "options": ["own", *TEAMS],
            "labels": {"own": "The triggering user's team", **{team: team.capitalize() for team in TEAMS}},
            "default": "own",
        },
        {"name": "points", "kind": "number", "label": "Points", "default": 0, "min": 0, "max": 1000},
        {**THREE_WAY, "name": "score_compare"},
    ),
    "wf_cnd_has_var": _box("condition", DOCUMENTED, VARIABLE, VARIABLE_ON, *HOLDERS),
    "wf_cnd_neg_has_var": _box("condition", DOCUMENTED, VARIABLE, VARIABLE_ON, *HOLDERS),
    "wf_cnd_var_val_match": _box(
        "condition",
        ASSUMED,
        VARIABLE,
        VARIABLE_ON,
        {**COMPARE, "default": ">"},
        VALUE,
        REFERENCE[0],
        *HOLDERS,
    ),
    "wf_cnd_trggrer_on_frn": _box("condition", DOCUMENTED, FURNI, USER_SOURCE),
    "wf_cnd_not_trggrer_on": _box("condition", DOCUMENTED, FURNI, USER_SOURCE),
    "wf_cnd_furnis_hv_avtrs": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_not_hv_avtrs": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_has_furni_on": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_not_furni_on": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_stuff_is": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_not_stuff_is": _box("condition", DOCUMENTED, FURNI),
    "wf_cnd_user_count_in": _box(
        "condition",
        DOCUMENTED,
        {"name": "min", "kind": "number", "label": "At least", "default": 1, "min": 0},
        {"name": "max", "kind": "number", "label": "At most", "default": 50, "min": 0},
    ),
    "wf_cnd_not_user_count": _box(
        "condition",
        DOCUMENTED,
        {"name": "min", "kind": "number", "label": "At least", "default": 1, "min": 0},
        {"name": "max", "kind": "number", "label": "At most", "default": 50, "min": 0},
    ),
    "wf_cnd_triggerer_match": _box(
        "condition", DOCUMENTED, {"name": "name", "kind": "text", "label": "Username", "default": ""}
    ),
    "wf_cnd_not_triggerer_match": _box(
        "condition", DOCUMENTED, {"name": "name", "kind": "text", "label": "Username", "default": ""}
    ),
    "wf_cnd_time_less_than": _box("condition", DOCUMENTED, SECONDS),
    "wf_cnd_time_more_than": _box("condition", DOCUMENTED, SECONDS),
    # Selectors
    "wf_slc_users_team": _selector(ASSUMED, ANY_TEAM),
    "wf_slc_furni_area": _selector(ASSUMED, *AREA),
    "wf_slc_users_area": _selector(ASSUMED, *AREA),
    "wf_slc_furni_altitude": _selector(
        ASSUMED,
        {
            "name": "altitude",
            "kind": "number",
            "label": "Height in tiles",
            "default": 0,
            "min": 0,
            "max": 80,
            "step": 0.01,
        },
        {
            "name": "altitude_compare",
            "kind": "select",
            "label": "Comparison",
            "options": ["less", "equal", "more"],
            "labels": {"less": "Lower than", "equal": "Exactly", "more": "Higher than"},
            "default": "less",
        },
    ),
    "wf_slc_furni_onfurni": _selector(
        ASSUMED,
        FURNI,
        {
            "name": "stacking",
            "kind": "select",
            "label": "Select the furni",
            "options": ["above", "below", "level", "tile"],
            "labels": {
                "above": "Above the picked furni",
                "below": "Under the picked furni",
                "level": "At the same height",
                "tile": "Anywhere on the same tile",
            },
            "default": "above",
        },
    ),
    "wf_slc_furni_picks": _selector(DOCUMENTED, FURNI),
    "wf_slc_furni_bytype": _selector(DOCUMENTED, FURNI),
    "wf_slc_furni_signal": _selector(DOCUMENTED),
    "wf_slc_furni_with_var": _selector(DOCUMENTED, VARIABLE),
    "wf_slc_users_signal": _selector(DOCUMENTED),
    "wf_slc_users_with_var": _selector(DOCUMENTED, VARIABLE),
    "wf_slc_users_onfurni": _selector(DOCUMENTED, FURNI),
    "wf_slc_users_handitem": _selector(
        DOCUMENTED,
        {"name": "handitem", "kind": "number", "label": "Hand Item", "default": 2, "min": 0},
    ),
    "wf_slc_users_bytype": _selector(
        DOCUMENTED,
        {
            "name": "types",
            "kind": "select",
            "label": "User type",
            "options": ["habbo", "pet", "bot", "habbo_pet", "habbo_bot", "pet_bot", "all"],
            "labels": {
                "habbo": "Habbo",
                "pet": "Pet",
                "bot": "Bot",
                "habbo_pet": "Habbo and Pet",
                "habbo_bot": "Habbo and Bot",
                "pet_bot": "Pet and Bot",
                "all": "Habbo, Pet and Bot",
            },
            "default": "habbo",
        },
    ),
    "wf_slc_users_byaction": _selector(DOCUMENTED, AVATAR_ACTION, ACTION_NUMBER),
    "wf_slc_users_neighborhood": _selector(DOCUMENTED, *NEIGHBOURHOOD),
    "wf_slc_furni_neighborhood": _selector(DOCUMENTED, *NEIGHBOURHOOD),
    "wf_slc_users_byname": _selector(
        DOCUMENTED,
        {"name": "names", "kind": "text", "label": "Names, one per line", "default": ""},
    ),
    # Add-ons
    "wf_xtra_exec_in_order": _box("addon", DOCUMENTED),
    "wf_xtra_random": _box(
        "addon",
        DOCUMENTED,
        _saved(
            {"name": "skip", "kind": "number", "label": "Effects to skip", "default": 0, "min": 0, "max": 100}
        ),
        _saved(
            {"name": "pick", "kind": "number", "label": "Effects to pick", "default": 1, "min": 1, "max": 100}
        ),
    ),
    "wf_xtra_unseen": _box("addon", DOCUMENTED),
    "wf_xtra_or_eval": _box("addon", DOCUMENTED),
    "wf_xtra_execution_limit": _box(
        "addon",
        DOCUMENTED,
        {"name": "count", "kind": "number", "label": "Runs allowed", "default": 100, "min": 1, "max": 100},
        {
            "name": "window_seconds",
            "kind": "number",
            "label": "Per this many seconds",
            "default": 0.5,
            "min": 0.5,
            "max": 10,
            "step": 0.5,
        },
    ),
    "wf_xtra_varfx_number": _box("addon", ASSUMED, *FX_COMMON),
    "wf_xtra_varfx_levelling": _box("addon", ASSUMED, *FX_COMMON),
    "wf_xtra_varfx_prog": _box("addon", ASSUMED, *FX_COMMON, *FX_RANGE),
    "wf_xtra_varfx_status": _box("addon", ASSUMED, *FX_COMMON, *FX_RANGE),
    "wf_xtra_varfx_hp": _box("addon", ASSUMED, *FX_COMMON, *FX_RANGE),
    "wf_xtra_varfx_boss": _box("addon", ASSUMED, *FX_COMMON, *FX_RANGE),
    "wf_xtra_rotate_to_dir": _box(
        "addon",
        ASSUMED,
        {"name": "proj_rotate", "kind": "bool", "label": "Turn to face the way it flies", "default": True},
        {
            "name": "proj_offset",
            "kind": "number",
            "label": "Extra turn, in eighths",
            "default": 0,
            "min": -7,
            "max": 7,
        },
        {"name": "proj_shooter", "kind": "bool", "label": "Turn the shooter too", "default": True},
        {"name": "proj_custom_time", "kind": "bool", "label": "Use a custom flight time", "default": False},
        {
            "name": "proj_tile_ms",
            "kind": "number",
            "label": "Milliseconds per tile",
            "default": 100,
            "min": 1,
            "max": 100000,
        },
        {
            "name": "proj_height",
            "kind": "number",
            "label": "Curve height",
            "default": 50,
            "min": -1000,
            "max": 1000,
        },
        {"name": "proj_past_on", "kind": "bool", "label": "Animate past the target", "default": False},
        {
            "name": "proj_past",
            "kind": "number",
            "label": "Tiles past the target",
            "default": 1,
            "min": -64,
            "max": 64,
        },
        _saved({"name": "proj_bunny", "kind": "bool", "label": "Bunny hop", "default": True}),
        _saved(
            {"name": "proj_variables", "kind": "number", "label": "Internal variables mask", "default": 0}
        ),
        FURNI_SOURCE,
        USER_SOURCE,
    ),
    "wf_xtra_mov_carry_users": _box(
        "addon",
        ASSUMED,
        _saved(
            {
                "name": "carry",
                "kind": "select",
                "label": "Carry",
                "options": ["furni", "tile"],
                "labels": {"furni": "Users on the furni", "tile": "Users on its tiles"},
                "default": "furni",
            }
        ),
        USER_SOURCE,
    ),
    # The movement add-ons change how this stack's moves look and what stops them. Habbo's labels.
    "wf_xtra_mov_no_animation": _box("addon", DOCUMENTED),
    "wf_xtra_anim_time": _box(
        "addon",
        DOCUMENTED,
        {
            "name": "anim_ms",
            "kind": "number",
            "label": "Animation time (ms)",
            "default": 500,
            "min": ANIM_MIN_MS,
            "max": ANIM_MAX_MS,
        },
    ),
    "wf_xtra_mov_curve": _box(
        "addon",
        DOCUMENTED,
        {
            "name": "curve_from_var",
            "kind": "bool",
            "label": "Take the strength from a variable",
            "default": False,
        },
        {
            "name": "curve",
            "kind": "number",
            "label": "Strength",
            "default": 160,
            "min": -CURVE_LIMIT,
            "max": CURVE_LIMIT,
        },
        VARIABLE,
        {
            "name": "curve_on",
            "kind": "select",
            "label": "Variable on",
            "options": ["context", "user", "furni", "global"],
            "labels": {"context": "Context", "user": "Users", "furni": "Furni", "global": "Room"},
            "default": "context",
        },
        FURNI,
        {**FURNI_SOURCE, "default": "picks"},
        {**USER_SOURCE, "options": ["trigger", "signal", "selector"], "default": "trigger"},
    ),
    "wf_xtra_mov_physics": _box(
        "addon",
        DOCUMENTED,
        {"name": "keep_altitude", "kind": "bool", "label": "Keep furni altitude", "default": True},
        {"name": "through_furni", "kind": "bool", "label": "Move through furniture", "default": False},
        {"name": "through_users", "kind": "bool", "label": "Move through users", "default": False},
        {"name": "blocked_by_furni", "kind": "bool", "label": "Is blocked by furniture", "default": False},
        {**FURNI, "name": "through_picks", "label": "Move through furni"},
        {**PHYSICS_FURNI, "name": "through_source", "label": "Move through furni from"},
        {**FURNI, "name": "blocking_picks", "label": "Blocked by furni"},
        {**PHYSICS_FURNI, "name": "blocking_source", "label": "Blocked by furni from"},
        {
            **USER_SOURCE,
            "label": "Move through users from",
            "options": ["room", "trigger", "signal", "selector"],
            "labels": {"room": "All users in the room"},
            "default": "room",
        },
    ),
    "wf_xtra_filter_users": _box("addon", DOCUMENTED, AMOUNT),
    "wf_xtra_filter_furni": _box("addon", DOCUMENTED, AMOUNT),
    "wf_xtra_filter_users_by_var": _box(
        "addon",
        DOCUMENTED,
        VARIABLE,
        AMOUNT,
        {"name": "lowest", "kind": "bool", "label": "Lowest instead of highest", "default": False},
    ),
    "wf_xtra_filter_furni_by_var": _box(
        "addon",
        DOCUMENTED,
        VARIABLE,
        AMOUNT,
        {"name": "lowest", "kind": "bool", "label": "Lowest instead of highest", "default": False},
    ),
    "wf_xtra_text_output_furni_name": _box(
        "addon",
        DOCUMENTED,
        {"name": "placeholder", "kind": "text", "label": "Placeholder name", "default": "name"},
        {
            "name": "type",
            "kind": "select",
            "label": "Placeholder type",
            "options": ["single", "multiple"],
            "labels": {"single": "Single furni", "multiple": "Multiple furnis"},
            "default": "single",
        },
        FURNI,
        {**FURNI_SOURCE, "label": "Furni from (default: the triggering furni)"},
    ),
    "wf_xtra_text_output_username": _box(
        "addon",
        DOCUMENTED,
        {"name": "placeholder", "kind": "text", "label": "Placeholder name", "default": "user"},
    ),
    "wf_xtra_text_output_variable": _box(
        "addon",
        ASSUMED,
        {"name": "placeholder", "kind": "text", "label": "Placeholder name", "default": ""},
        VARIABLE,
        VARIABLE_ON,
        _saved(
            {
                "name": "display",
                "kind": "select",
                "label": "Variable display type",
                "options": ["numeric", "textual"],
                "labels": {"numeric": "Numeric", "textual": "Textual, with a Text Connector"},
                "default": "numeric",
            }
        ),
        _saved(
            {
                "name": "placeholder_type",
                "kind": "select",
                "label": "Placeholder type",
                "options": ["single", "multiple"],
                "labels": {"single": "Single", "multiple": "Multiple"},
                "default": "single",
            }
        ),
        _saved({"name": "delimiter", "kind": "text", "label": "Delimiter, for Multiple", "default": ""}),
    ),
    "wf_xtra_var_text_connector": _box(
        "addon",
        ASSUMED,
        VARIABLE,
        {"name": "mapping", "kind": "textarea", "label": "Values, such as 3=carrot", "default": ""},
    ),
    "wf_xtra_var_time_util": _box("addon", DOCUMENTED, VARIABLE),
    # Variable definitions
    "wf_var_user": _box(
        "variable", DOCUMENTED, VARIABLE, _availability("active", "persistent", "shared"), HAS_VALUE
    ),
    "wf_var_furni": _box("variable", DOCUMENTED, VARIABLE, HAS_VALUE, _availability("active", "persistent")),
    "wf_var_room": _box("variable", DOCUMENTED, VARIABLE, _availability("active", "persistent", "shared")),
    "wf_var_context": _box("variable", ASSUMED, VARIABLE, HAS_VALUE),
    "wf_var_echo": _box(
        "variable",
        DOCUMENTED,
        VARIABLE,
        {"name": "source", "kind": "text", "label": "Variable it echoes", "default": ""},
    ),
    "wf_var_pointer": _box(
        "variable",
        DOCUMENTED,
        VARIABLE,
        {
            "name": "target",
            "kind": "select",
            "label": "Points to a variable on",
            "options": ["user", "furni", "global", "context"],
            "labels": {"user": "Users", "furni": "Furni", "global": "Room", "context": "Context"},
            "default": "user",
        },
        {"name": "accessor", "kind": "text", "label": "Context accessor variable", "default": ""},
    ),
    "wf_trg_clock_counter": _box("trigger", ASSUMED, FURNI, *CLOCK_TIME),
    "wf_trg_game_starts": _box("trigger", ASSUMED),
    "wf_trg_game_ends": _box("trigger", ASSUMED),
    # Effects
    "wf_act_give_var": _effect(ASSUMED, VARIABLE, VARIABLE_ON, VALUE, REFERENCE[0], OVERWRITE, *HOLDERS),
    "wf_act_remove_var": _effect(DOCUMENTED, VARIABLE, VARIABLE_ON, *HOLDERS),
    "wf_act_change_var_val": _effect(
        ASSUMED,
        VARIABLE,
        VARIABLE_ON,
        {
            "name": "operation",
            "kind": "select",
            "label": "Operation",
            "options": list(OPERATION_LABELS),
            "labels": OPERATION_LABELS,
            "default": "set",
        },
        VALUE,
        *REFERENCE,
        *HOLDERS,
    ),
    "wf_act_send_signal": _effect(DOCUMENTED, ANTENNA, USER_SOURCE, SPLIT_USERS),
    "wf_act_neg_send_signal": _effect(ASSUMED, ANTENNA, USER_SOURCE, SPLIT_USERS),
    "wf_act_call_stacks": _effect(DOCUMENTED, FURNI),
    "wf_act_neg_call_stacks": _effect(ASSUMED, FURNI),
    "wf_act_toggle_state": _effect(
        DOCUMENTED,
        FURNI,
        FURNI_SOURCE,
        _saved(
            {
                "name": "toggle_type",
                "kind": "select",
                "label": "Toggle to the",
                "options": ["next", "previous"],
                "default": "next",
            }
        ),
    ),
    "wf_act_toggle_to_rnd": _effect(DOCUMENTED, FURNI, FURNI_SOURCE),
    "wf_act_send_message": _effect(
        ASSUMED,
        {
            "name": "message_source",
            "kind": "select",
            "label": "Message source",
            "options": ["trigger", "custom"],
            "labels": {"trigger": "From WIRED trigger", "custom": "Custom message"},
            "default": "trigger",
        },
        {"name": "text", "kind": "text", "label": "Custom message", "default": ""},
        LINKS,
        {**FURNI_SOURCE, "label": "WIRED Links from"},
    ),
    "wf_act_show_message": _effect(
        DOCUMENTED, {"name": "text", "kind": "text", "label": "Message", "default": ""}, USER_SOURCE
    ),
    "wf_act_log": _effect(
        ASSUMED, {"name": "text", "kind": "text", "label": "Log line", "default": ""}, LOG_LEVEL
    ),
    "wf_act_neg_log": _effect(ASSUMED, {"name": "text", "kind": "text", "label": "Log line", "default": ""}),
    "wf_act_reset_timers": _effect(DOCUMENTED),
    "wf_act_teleport_to": _effect(DOCUMENTED, FURNI, USER_SOURCE),
    "wf_act_user_to_furni": _effect(
        ASSUMED,
        _saved(
            {
                "name": "walking",
                "kind": "select",
                "label": "If the user was walking",
                "options": ["closer", "keep", "stop"],
                "labels": {
                    "closer": "Keep walking if moved closer to target",
                    "keep": "Keep walking",
                    "stop": "Stop walking",
                },
                "default": "closer",
            }
        ),
        FURNI,
        USER_SOURCE,
    ),
    "wf_act_control_clock": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        {
            "name": "clock_control",
            "kind": "select",
            "label": "Command",
            "options": ["start", "stop", "reset", "pause", "resume"],
            "labels": {
                "start": "Start",
                "stop": "Stop",
                "reset": "Reset",
                "pause": "Pause",
                "resume": "Resume",
            },
            "default": "start",
        },
    ),
    "wf_act_adjust_clock": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        *CLOCK_TIME,
        {
            "name": "clock_change",
            "kind": "select",
            "label": "Change",
            "options": ["add", "subtract", "set"],
            "labels": {"add": "Add", "subtract": "Take away", "set": "Set to"},
            "default": "add",
        },
    ),
    "wf_act_set_highlight": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        TARGET_KIND,
        AUDIENCE,
        USER_SOURCE,
        {
            "name": "highlight_type",
            "kind": "select",
            "label": "Look",
            "options": ["outline", "glow", "darken", "tint", "brighten"],
            "labels": {
                "outline": "Outline",
                "glow": "Glow",
                "darken": "Darken",
                "tint": "Colour tint",
                "brighten": "Brighten",
            },
            "default": "outline",
        },
        {"name": "strength", "kind": "number", "label": "Strength", "default": 100, "min": 0, "max": 100},
        {
            "name": "color",
            "kind": "number",
            "label": "Colour number",
            "default": 16771584,
            "min": 0,
            "max": 16771584,
        },
        {"name": "pulse", "kind": "bool", "label": "Pulse", "default": False},
        _saved(EASING),
    ),
    "wf_act_set_visibility": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        TARGET_KIND,
        AUDIENCE,
        USER_SOURCE,
        {
            "name": "visibility",
            "kind": "select",
            "label": "Make it",
            "options": ["invisible", "visible"],
            "labels": {"invisible": "Invisible", "visible": "Visible"},
            "default": "invisible",
        },
        {"name": "click_through", "kind": "bool", "label": "Let clicks pass through", "default": False},
        _saved(EASING),
    ),
    "wf_act_join_team": _effect(
        ASSUMED,
        TEAM,
        _saved(
            {
                "name": "team_type",
                "kind": "select",
                "label": "Kind of team",
                "options": ["wired", "banzai", "freeze"],
                "labels": {"wired": "Wired", "banzai": "Battle Banzai", "freeze": "Freeze"},
                "default": "wired",
            }
        ),
        USER_SOURCE,
    ),
    "wf_act_leave_team": _effect(ASSUMED, USER_SOURCE),
    "wf_act_give_score": _effect(ASSUMED, *POINTS, USER_SOURCE),
    "wf_act_give_score_tm": _effect(ASSUMED, *POINTS, TEAM),
    "wf_act_rel_mov": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        {"name": "move_x", "kind": "number", "label": "Tiles along x", "default": 0, "min": -20, "max": 20},
        {"name": "move_y", "kind": "number", "label": "Tiles along y", "default": 0, "min": -20, "max": 20},
    ),
    "wf_act_set_altitude": _effect(
        ASSUMED,
        FURNI,
        FURNI_SOURCE,
        {
            "name": "altitude",
            "kind": "number",
            "label": "Height in tiles",
            "default": 0,
            "min": 0,
            "max": 80,
            "step": 0.01,
        },
        {
            "name": "altitude_change",
            "kind": "select",
            "label": "Change",
            "options": ["raise", "lower", "set"],
            "labels": {"raise": "Raise by", "lower": "Lower by", "set": "Set to"},
            "default": "raise",
        },
    ),
    "wf_act_furni_to_user": _effect(ASSUMED, FURNI, FURNI_SOURCE, USER_SOURCE),
    "wf_act_furni_to_furni": _effect(ASSUMED, {**FURNI, "label": "Move onto"}, MOVERS),
    "wf_act_move_rotate_user": _effect(
        ASSUMED,
        USER_SOURCE,
        {
            "name": "user_move",
            "kind": "select",
            "label": "Move",
            "options": ["none", *COMPASS],
            "labels": {"none": "Don't move", **COMPASS},
            "default": "none",
        },
        {
            "name": "user_turn",
            "kind": "select",
            "label": "Turn",
            "options": ["none", *COMPASS, "clockwise", "counterclockwise"],
            "labels": {
                "none": "Don't turn",
                **{name: f"Face {label}" for name, label in COMPASS.items()},
                "clockwise": "One step clockwise",
                "counterclockwise": "One step counterclockwise",
            },
            "default": "none",
        },
    ),
    "wf_act_chase": _effect(DOCUMENTED, FURNI, FURNI_SOURCE),
    "wf_act_flee": _effect(DOCUMENTED, FURNI, FURNI_SOURCE),
    "wf_act_move_to_dir": _effect(
        DOCUMENTED,
        FURNI,
        FURNI_SOURCE,
        {
            "name": "start_dir",
            "kind": "select",
            "label": "Start direction",
            "options": ["0", "1", "2", "3", "4", "5", "6", "7"],
            "labels": {
                "0": "Up right (y-)",
                "1": "Right (x+ y-)",
                "2": "Down right (x+)",
                "3": "Down (x+ y+)",
                "4": "Down left (y+)",
                "5": "Left (x- y+)",
                "6": "Up left (x-)",
                "7": "Up (x- y-)",
            },
            "default": "0",
        },
        {
            "name": "turn",
            "kind": "select",
            "label": "When move is blocked",
            "options": ["wait", "right_45", "right_90", "left_45", "left_90", "back", "random"],
            "labels": {
                "wait": "Wait",
                "right_45": "Turn right 45 degrees",
                "right_90": "Turn right 90 degrees",
                "left_45": "Turn left 45 degrees",
                "left_90": "Turn left 90 degrees",
                "back": "Turn back",
                "random": "Turn to a random direction",
            },
            "default": "wait",
        },
        {
            "name": "block_users",
            "kind": "bool",
            "label": "A user in the way stops the furni",
            "default": True,
        },
    ),
    "wf_act_move_rotate": _effect(
        DOCUMENTED,
        FURNI,
        FURNI_SOURCE,
        {
            "name": "direction",
            "kind": "select",
            "label": "Move",
            "options": ["none", *COMPASS, "random", "random_x", "random_y"],
            "labels": {
                "none": "Don't move",
                **COMPASS,
                "random": "Any random way",
                "random_x": "Randomly along x",
                "random_y": "Randomly along y",
            },
            "default": "none",
        },
        {
            "name": "rotation",
            "kind": "select",
            "label": "Rotate",
            "options": ["none", "clockwise", "counterclockwise", "random"],
            "default": "none",
        },
    ),
}


def is_box(classname: str) -> bool:
    """Whether a wf_ name is a WIRED box. Tiles, tokens and wires share the prefix but hold no WIRED logic."""
    return re.search(r"(?:^|_)(trg|act|cnd|slc|xtra|var)(?:_|$)", classname[3:]) is not None


def catalogue() -> dict[str, dict[str, Any]]:
    return BOXES
