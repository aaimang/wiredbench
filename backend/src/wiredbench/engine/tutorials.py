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

    # The calculator. Boxes run from the top of the stack down, so they are listed last to first.
    from_signal = {"user_source": "signal"}
    stack(
        1,
        2,
        ("wf_trg_recv_signal", {"antenna": [ANTENNA_CALC]}),
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
        ("wf_xtra_exec_in_order", {}),
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
        ("wf_act_send_signal", {"antenna": [ANTENNA_CALC], "user_source": "selector"}),
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
