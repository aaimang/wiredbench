"""Example rooms. Built from settings here, because no G-Presets file exists for them.

The time tracking room follows baikal's article "Habbo Wired: Time Tracking System":
https://baikal-de.medium.com/habbo-wired-time-tracking-system-c32286da1195

The article's screenshots hold some exact settings, so effect order and values are this project's reading
of its text.
"""

from __future__ import annotations

from typing import Any

SEAT = 1
ANTENNA_CALC = 2
ANTENNA_CHECK = 3
AVATAR = 500
FIGURE = "hd-180-1.ch-210-66.lg-270-82.sh-290-91.hr-100-61"
KEYWORD = ":time"
SYNC_SECONDS = 10


def time_tracking(hotel: str = "sandbox") -> dict[str, Any]:
    next_id = [10]
    furni: list[dict[str, Any]] = [
        {"id": SEAT, "classname": "chair_norja", "x": 4, "y": 4, "z": 0, "rot": 2, "state": 0},
        {"id": ANTENNA_CALC, "classname": "wf_antenna1", "x": 6, "y": 0, "z": 0, "rot": 0, "state": 0},
        {"id": ANTENNA_CHECK, "classname": "wf_antenna2", "x": 7, "y": 0, "z": 0, "rot": 0, "state": 0},
    ]

    def stack(x: int, y: int, *boxes: tuple[str, dict[str, Any]]) -> None:
        z = 0.0
        for classname, settings in boxes:
            furni.append(
                {
                    "id": next_id[0],
                    "classname": classname,
                    "x": x,
                    "y": y,
                    "z": round(z, 2),
                    "rot": 0,
                    "state": 0,
                    "wired": settings,
                }
            )
            next_id[0] += 1
            z += 0.65

    def var(name: str) -> tuple[str, dict[str, Any]]:
        return "wf_var_user", {"variable": name}

    def time_util(name: str) -> tuple[str, dict[str, Any]]:
        return "wf_xtra_var_time_util", {"variable": name}

    stack(0, 0, var("seconds"), time_util("seconds"))
    stack(1, 0, var("on_duty"), time_util("on_duty"))
    stack(2, 0, var("last_duty"), time_util("last_duty"))
    stack(3, 0, var("tmp"), time_util("tmp"))

    # Sitting down marks the user as active. Overwriting also renews the timestamp.
    stack(
        0,
        2,
        ("wf_trg_walks_on_furni", {"furni": [SEAT]}),
        ("wf_act_give_var", {"variable": "on_duty", "overwrite": True}),
    )

    # The calculator. Boxes run from the bottom of the stack up. They read best last to first, so they are reversed.
    from_signal = {"user_source": "signal"}
    calculator: list[tuple[str, dict[str, Any]]] = [
        ("wf_act_send_signal", {"antenna": [ANTENNA_CHECK], **from_signal}),
        (
            "wf_act_change_var_val",
            {"variable": "seconds", "operation": "add", "from_variable": "tmp", **from_signal},
        ),
        (
            "wf_act_change_var_val",
            {"variable": "tmp", "operation": "subtract", "from_variable": "last_duty", **from_signal},
        ),
        (
            "wf_act_change_var_val",
            {
                "variable": "tmp",
                "operation": "set",
                "from_variable": "last_duty",
                "from_field": "creation",
                **from_signal,
            },
        ),
        ("wf_act_give_var", {"variable": "tmp", "overwrite": True, **from_signal}),
        (
            "wf_act_change_var_val",
            {
                "variable": "last_duty",
                "operation": "set",
                "from_variable": "on_duty",
                "from_field": "creation",
                **from_signal,
            },
        ),
        ("wf_act_give_var", {"variable": "last_duty", "overwrite": True, **from_signal}),
        ("wf_act_give_var", {"variable": "seconds", **from_signal}),
    ]
    stack(
        1,
        2,
        ("wf_trg_recv_signal", {"antenna": [ANTENNA_CALC]}),
        ("wf_xtra_exec_in_order", {}),
        *reversed(calculator),
    )

    # Still on the seat: renew on_duty. Gone: remove it.
    stack(
        2,
        2,
        ("wf_trg_recv_signal", {"antenna": [ANTENNA_CHECK]}),
        ("wf_cnd_trggrer_on_frn", {"furni": [SEAT], **from_signal}),
        ("wf_act_give_var", {"variable": "on_duty", "overwrite": True, **from_signal}),
    )
    stack(
        3,
        2,
        ("wf_trg_recv_signal", {"antenna": [ANTENNA_CHECK]}),
        ("wf_cnd_not_trggrer_on", {"furni": [SEAT], **from_signal}),
        ("wf_act_remove_var", {"variable": "on_duty", **from_signal}),
    )

    # Everything that starts the calculator.
    stack(
        5,
        2,
        ("wf_trg_periodically", {"seconds": SYNC_SECONDS}),
        ("wf_slc_users_with_var", {"variable": "on_duty"}),
        ("wf_act_send_signal", {"antenna": [ANTENNA_CALC], "user_source": "selector", "split_users": True}),
    )
    stack(
        6,
        2,
        ("wf_trg_walks_off_furni", {"furni": [SEAT]}),
        ("wf_act_send_signal", {"antenna": [ANTENNA_CALC], "user_source": "trigger"}),
    )
    stack(
        7,
        2,
        ("wf_trg_says_something", {"text": KEYWORD}),
        ("wf_cnd_has_var", {"variable": "on_duty", "user_source": "trigger"}),
        ("wf_act_send_signal", {"antenna": [ANTENNA_CALC], "user_source": "trigger"}),
    )

    return {
        "schema": 1,
        "room": {"width": 10, "height": 10},
        "furni": furni,
        "avatars": [
            {
                "id": AVATAR,
                "name": "Worker",
                "hotel": hotel,
                "figure": FIGURE,
                "x": 4,
                "y": 6,
                "z": 0,
                "dir": 0,
                "pose": "std",
            }
        ],
    }


def _box(furni_id: int, classname: str, x: int, y: int, z: float, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": furni_id,
        "classname": classname,
        "x": x,
        "y": y,
        "z": z,
        "rot": 0,
        "state": 0,
        "wired": settings,
    }


def _plain(furni_id: int, classname: str, x: int, y: int) -> dict[str, Any]:
    return {"id": furni_id, "classname": classname, "x": x, "y": y, "z": 0, "rot": 0, "state": 0}


def _visitor(hotel: str, x: int = 4, y: int = 6) -> dict[str, Any]:
    return {
        "id": AVATAR,
        "name": "Visitor",
        "hotel": hotel,
        "figure": FIGURE,
        "x": x,
        "y": y,
        "z": 0,
        "dir": 0,
        "pose": "std",
    }


def switch_flip(hotel: str = "sandbox") -> dict[str, Any]:
    """A switch and a candle, because Toggle Furni State leaves floor switches as they are in a real room."""
    return {
        "schema": 1,
        "room": {"width": 10, "height": 10},
        "furni": [
            _plain(1, "wf_floor_switch1", 2, 4),
            _plain(2, "rela_candle1", 6, 4),
            _box(3, "wf_trg_state_changed", 4, 2, 0, {"furni": [1]}),
            _box(4, "wf_act_toggle_state", 4, 2, 0.65, {"furni": [2]}),
        ],
        # A floor switch works only from a tile next to it, so the visitor starts there.
        "avatars": [_visitor(hotel, 3, 5)],
    }


def signal_relay(hotel: str = "sandbox") -> dict[str, Any]:
    return {
        "schema": 1,
        "room": {"width": 10, "height": 10},
        "furni": [
            _plain(1, "wf_floor_switch1", 2, 4),
            _plain(2, "rela_candle1", 6, 4),
            _plain(3, "wf_antenna1", 4, 0),
            _box(4, "wf_trg_state_changed", 2, 2, 0, {"furni": [1]}),
            _box(5, "wf_act_send_signal", 2, 2, 0.65, {"antenna": [3], "user_source": "trigger"}),
            _box(6, "wf_trg_recv_signal", 6, 2, 0, {"antenna": [3]}),
            _box(7, "wf_act_toggle_state", 6, 2, 0.65, {"furni": [2]}),
        ],
        "avatars": [_visitor(hotel, 3, 5)],
    }


def score_counter(hotel: str = "sandbox") -> dict[str, Any]:
    # Boxes run from the bottom of the stack up, so giving the variable sits below adding to it.
    add = {"variable": "score", "operation": "add", "value": 1, "user_source": "trigger"}
    return {
        "schema": 1,
        "room": {"width": 10, "height": 10},
        "furni": [
            _box(1, "wf_var_user", 0, 0, 0, {"variable": "score"}),
            _box(2, "wf_trg_says_something", 3, 2, 0, {"text": "point"}),
            _box(4, "wf_act_give_var", 3, 2, 0.65, {"variable": "score", "user_source": "trigger"}),
            _box(3, "wf_act_change_var_val", 3, 2, 1.3, add),
            _box(5, "wf_xtra_exec_in_order", 3, 2, 1.95, {}),
        ],
        "avatars": [_visitor(hotel)],
    }


def visitor_view(hotel: str = "sandbox") -> dict[str, Any]:
    """One keyword per effect a visitor should see, so View as user can be checked by eye."""
    everyone = {"audience": "everyone"}

    def said(stack: int, text: str, *effects: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        boxes = [
            _box(100 + stack * 10, "wf_trg_says_something", stack, 0, 0, {"text": text, "match": "exact"})
        ]
        for n, (classname, settings) in enumerate(effects, 1):
            boxes.append(_box(100 + stack * 10 + n, classname, stack, 0, round(0.65 * n, 2), settings))
        return boxes

    throw: tuple[str, dict[str, Any]] = ("wf_xtra_rotate_to_dir", {})
    step: tuple[str, dict[str, Any]] = ("wf_act_move_rotate_user", {"user_move": "x+"})
    return {
        "schema": 1,
        "room": {"width": 12, "height": 12},
        "furni": [
            _plain(1, "chair_norja", 1, 4),
            _plain(2, "chair_norja", 1, 7),
            _plain(3, "rela_candle1", 9, 4),
            _plain(4, "wf_floor_switch1", 9, 7),
            *said(0, "throw", ("wf_act_rel_mov", {"furni": [1], "move_x": 4}), throw),
            *said(1, "throw back", ("wf_act_rel_mov", {"furni": [1], "move_x": -4}), throw),
            *said(2, "slide", ("wf_act_rel_mov", {"furni": [2], "move_x": 2})),
            *said(3, "slide back", ("wf_act_rel_mov", {"furni": [2], "move_x": -2})),
            *said(4, "glow", ("wf_act_set_highlight", {"furni": [3], **everyone})),
            *said(
                5, "hide", ("wf_act_set_visibility", {"furni": [3], "visibility": "invisible", **everyone})
            ),
            *said(6, "show", ("wf_act_set_visibility", {"furni": [3], "visibility": "visible", **everyone})),
            *said(7, "hp", ("wf_act_give_var", {"variable": "hp", "value": 40, "user_source": "trigger"})),
            *said(8, "step", step),
            *said(9, "jump", step, step, step),
            _box(200, "wf_trg_click_furni", 10, 0, 0, {"furni": [4]}),
            _box(201, "wf_act_show_message", 10, 0, 0.65, {"text": "You clicked the switch."}),
            _box(210, "wf_trg_state_changed", 11, 0, 0, {"furni": [4]}),
            _box(211, "wf_act_toggle_state", 11, 0, 0.65, {"furni": [3]}),
            _box(220, "wf_var_user", 0, 2, 0, {"variable": "hp"}),
            _box(221, "wf_xtra_varfx_number", 0, 2, 0.65, {}),
        ],
        "avatars": [_visitor(hotel)],
    }


TUTORIALS: dict[str, dict[str, Any]] = {
    "switch-flip": {
        "title": "Switch flips a switch",
        "description": "One trigger and one effect. This is the setup that has been tried in a real room.",
        "try": "Press Run, then double-click the left switch.",
        "build": switch_flip,
    },
    "signal-relay": {
        "title": "Signal relay",
        "description": "One stack sends a signal through an antenna, and another stack reacts to it.",
        "try": "Press Run, double-click the left switch, and watch the trace.",
        "build": signal_relay,
    },
    "score-counter": {
        "title": "Score counter",
        "description": "A user variable that goes up each time someone says a keyword.",
        "try": "Press Run, say point, and watch score in the variables table.",
        "build": score_counter,
    },
    "visitor-view": {
        "title": "Visitor view test",
        "description": "One keyword per effect a visitor should see: throws, slides, highlights, hiding and numbers.",
        "try": (
            "Open it in View as user and say throw, throw back, slide, slide back, glow, hide, show, hp, "
            "step or jump. Click the switch for a message, and double-click it to light the candle."
        ),
        "build": visitor_view,
    },
    "time-tracking": {
        "title": "Time tracking example",
        "description": "A larger room that counts time spent on a seat, from baikal's article.",
        "try": "Press Run, walk onto the chair, wait, then say :time.",
        "build": time_tracking,
    },
}
