"""What the engine knows about each WIRED box: its settings and how far its behaviour can be trusted.

Fidelity is deliberately plain. `documented` means a public source describes the behaviour, though details
may still differ. `assumed` means the behaviour is a best guess. Nothing is `verified` until it has been
compared with a real room. Boxes not listed here are placed as logging stubs.
"""

from __future__ import annotations

from typing import Any

DOCUMENTED = "documented"
ASSUMED = "assumed"
DEFAULT_DELAY = {
    "name": "delay",
    "kind": "number",
    "label": "Delay (half seconds)",
    "default": 0,
    "min": 0,
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
AMOUNT = {"name": "amount", "kind": "number", "label": "How many", "default": 1, "min": 0}
ANTENNA = {"name": "antenna", "kind": "furni", "label": "Antenna", "default": []}
SECONDS = {"name": "seconds", "kind": "number", "label": "Seconds", "default": 10, "min": 0}


def _box(kind: str, fidelity: str, *fields: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "fidelity": fidelity, "fields": list(fields)}


def _effect(fidelity: str, *fields: dict[str, Any]) -> dict[str, Any]:
    return _box("effect", fidelity, *fields, DEFAULT_DELAY)


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
        {"name": "text", "kind": "text", "label": "Keyword", "default": ""},
        {"name": "exact", "kind": "bool", "label": "Whole message must match", "default": False},
    ),
    "wf_trg_enter_room": _box("trigger", DOCUMENTED),
    "wf_trg_leave_room": _box("trigger", ASSUMED),
    "wf_trg_room_initializes": _box("trigger", ASSUMED),
    "wf_trg_periodically": _box("trigger", DOCUMENTED, SECONDS),
    "wf_trg_period_short": _box("trigger", ASSUMED, SECONDS),
    "wf_trg_period_long": _box("trigger", DOCUMENTED, SECONDS),
    "wf_trg_at_given_time": _box("trigger", DOCUMENTED, SECONDS),
    "wf_trg_recv_signal": _box("trigger", DOCUMENTED, ANTENNA),
    "wf_trg_var_changed": _box("trigger", ASSUMED, VARIABLE),
    # Conditions
    "wf_cnd_has_var": _box("condition", DOCUMENTED, VARIABLE, USER_SOURCE),
    "wf_cnd_neg_has_var": _box("condition", DOCUMENTED, VARIABLE, USER_SOURCE),
    "wf_cnd_var_val_match": _box("condition", ASSUMED, VARIABLE, COMPARE, VALUE, USER_SOURCE),
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
        {"name": "min", "kind": "number", "label": "At least", "default": 0, "min": 0},
        {"name": "max", "kind": "number", "label": "At most", "default": 50, "min": 0},
    ),
    "wf_cnd_not_user_count": _box(
        "condition",
        DOCUMENTED,
        {"name": "min", "kind": "number", "label": "At least", "default": 0, "min": 0},
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
    "wf_slc_furni_picks": _box("selector", DOCUMENTED, FURNI),
    "wf_slc_furni_bytype": _box("selector", DOCUMENTED, FURNI),
    "wf_slc_furni_signal": _box("selector", DOCUMENTED),
    "wf_slc_furni_with_var": _box("selector", DOCUMENTED, VARIABLE),
    "wf_slc_users_signal": _box("selector", DOCUMENTED),
    "wf_slc_users_with_var": _box("selector", DOCUMENTED, VARIABLE),
    "wf_slc_users_onfurni": _box("selector", DOCUMENTED, FURNI),
    "wf_slc_users_byname": _box(
        "selector",
        DOCUMENTED,
        {"name": "names", "kind": "text", "label": "Names, one per line", "default": ""},
    ),
    # Add-ons
    "wf_xtra_exec_in_order": _box("addon", DOCUMENTED),
    "wf_xtra_random": _box("addon", DOCUMENTED),
    "wf_xtra_unseen": _box("addon", DOCUMENTED),
    "wf_xtra_or_eval": _box("addon", DOCUMENTED),
    "wf_xtra_execution_limit": _box(
        "addon",
        DOCUMENTED,
        {"name": "count", "kind": "number", "label": "Runs allowed", "default": 10, "min": 1},
        {
            "name": "window_seconds",
            "kind": "number",
            "label": "Per this many seconds",
            "default": 1,
            "min": 1,
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
    ),
    "wf_xtra_var_text_connector": _box(
        "addon",
        ASSUMED,
        VARIABLE,
        {"name": "mapping", "kind": "textarea", "label": "Values, such as 3=carrot", "default": ""},
    ),
    "wf_xtra_var_time_util": _box("addon", DOCUMENTED, VARIABLE),
    # Variable definitions
    "wf_var_user": _box("variable", DOCUMENTED, VARIABLE),
    "wf_var_furni": _box("variable", DOCUMENTED, VARIABLE),
    "wf_var_room": _box("variable", DOCUMENTED, VARIABLE),
    "wf_var_context": _box("variable", ASSUMED, VARIABLE),
    # Effects
    "wf_act_give_var": _effect(ASSUMED, VARIABLE, VALUE, OVERWRITE, USER_SOURCE),
    "wf_act_remove_var": _effect(DOCUMENTED, VARIABLE, USER_SOURCE),
    "wf_act_change_var_val": _effect(
        ASSUMED,
        VARIABLE,
        {
            "name": "operation",
            "kind": "select",
            "label": "Operation",
            "options": ["set", "add", "subtract", "multiply", "divide"],
            "default": "set",
        },
        VALUE,
        *REFERENCE,
        USER_SOURCE,
    ),
    "wf_act_send_signal": _effect(DOCUMENTED, ANTENNA, USER_SOURCE),
    "wf_act_neg_send_signal": _effect(ASSUMED, ANTENNA, USER_SOURCE),
    "wf_act_call_stacks": _effect(DOCUMENTED, FURNI),
    "wf_act_neg_call_stacks": _effect(ASSUMED, FURNI),
    "wf_act_toggle_state": _effect(DOCUMENTED, FURNI, FURNI_SOURCE),
    "wf_act_toggle_to_rnd": _effect(DOCUMENTED, FURNI, FURNI_SOURCE),
    "wf_act_show_message": _effect(
        DOCUMENTED, {"name": "text", "kind": "text", "label": "Message", "default": ""}, USER_SOURCE
    ),
    "wf_act_log": _effect(ASSUMED, {"name": "text", "kind": "text", "label": "Log line", "default": ""}),
    "wf_act_neg_log": _effect(ASSUMED, {"name": "text", "kind": "text", "label": "Log line", "default": ""}),
    "wf_act_reset_timers": _effect(DOCUMENTED),
    "wf_act_teleport_to": _effect(DOCUMENTED, FURNI, USER_SOURCE),
    "wf_act_user_to_furni": _effect(ASSUMED, FURNI, USER_SOURCE),
    "wf_act_move_rotate": _effect(
        DOCUMENTED,
        FURNI,
        FURNI_SOURCE,
        {
            "name": "direction",
            "kind": "select",
            "label": "Move",
            "options": ["none", "x+", "x-", "y+", "y-"],
            "default": "none",
        },
        {
            "name": "rotation",
            "kind": "select",
            "label": "Rotate",
            "options": ["none", "clockwise", "counterclockwise"],
            "default": "none",
        },
    ),
}


def catalogue() -> dict[str, dict[str, Any]]:
    return BOXES
