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
    # Conditions
    "wf_cnd_var_age_match": _box(
        "condition",
        ASSUMED,
        VARIABLE,
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
    "wf_xtra_filter_users": _box("addon", DOCUMENTED, AMOUNT),
    "wf_xtra_filter_furni": _box("addon", DOCUMENTED, AMOUNT),
    "wf_xtra_filter_users_by_var": _box(
        "addon",
        DOCUMENTED,
        VARIABLE,
        AMOUNT,
        {"name": "lowest", "kind": "bool", "label": "Lowest instead of highest", "default": False},
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
    "wf_trg_clock_counter": _box("trigger", ASSUMED, FURNI, *CLOCK_TIME),
    "wf_trg_game_starts": _box("trigger", ASSUMED),
    "wf_trg_game_ends": _box("trigger", ASSUMED),
    # Effects
    "wf_act_give_var": _effect(ASSUMED, VARIABLE, VALUE, REFERENCE[0], OVERWRITE, *HOLDERS),
    "wf_act_remove_var": _effect(DOCUMENTED, VARIABLE, *HOLDERS),
    "wf_act_change_var_val": _effect(
        ASSUMED,
        VARIABLE,
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
