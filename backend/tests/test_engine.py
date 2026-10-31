from __future__ import annotations

from typing import Any

import pytest

from wiredbench.engine.core import INT64_MAX, Engine, replay
from wiredbench.engine.tutorials import ANTENNA_CALC, AVATAR, KEYWORD, SEAT, SYNC_SECONDS, time_tracking

SECOND = 1000


def seconds(engine: Engine) -> int:
    holding = engine.variables["seconds"].get(f"user:{AVATAR}")
    return holding.value if holding else 0


def on_duty(engine: Engine) -> bool:
    return f"user:{AVATAR}" in engine.variables["on_duty"]


def sit(engine: Engine) -> None:
    engine.apply_input({"type": "move", "user": AVATAR, "x": 4, "y": 4})


def stand(engine: Engine) -> None:
    engine.apply_input({"type": "move", "user": AVATAR, "x": 4, "y": 5})


@pytest.fixture
def tutorial() -> Engine:
    return Engine(time_tracking())


# --- The acceptance test: the system from baikal's time tracking article ---


def test_sitting_marks_user_on_duty(tutorial: Engine) -> None:
    assert not on_duty(tutorial)
    sit(tutorial)
    assert on_duty(tutorial)


def test_time_is_banked_every_ten_seconds_while_seated(tutorial: Engine) -> None:
    tutorial.advance(3 * SECOND)
    sit(tutorial)
    tutorial.advance(SYNC_SECONDS * SECOND - 3 * SECOND - 1)
    assert seconds(tutorial) == 0, "the first sync has not happened yet"
    tutorial.advance(1)
    assert seconds(tutorial) == SYNC_SECONDS - 3
    tutorial.advance(SYNC_SECONDS * SECOND)
    assert seconds(tutorial) == 2 * SYNC_SECONDS - 3
    assert on_duty(tutorial), "still seated"


def test_standing_up_banks_the_time_and_ends_the_shift(tutorial: Engine) -> None:
    sit(tutorial)
    tutorial.advance(14 * SECOND)
    stand(tutorial)
    assert seconds(tutorial) == 14
    assert not on_duty(tutorial)
    tutorial.advance(60 * SECOND)
    assert seconds(tutorial) == 14, "no more time after standing"


def test_keyword_syncs_at_once_only_while_on_duty(tutorial: Engine) -> None:
    tutorial.apply_input({"type": "say", "user": AVATAR, "text": KEYWORD})
    assert seconds(tutorial) == 0, "the Has Variable condition blocks it"
    sit(tutorial)
    tutorial.advance(7 * SECOND)
    tutorial.apply_input({"type": "say", "user": AVATAR, "text": KEYWORD})
    assert seconds(tutorial) == 7
    assert on_duty(tutorial)
    tutorial.advance(3 * SECOND)
    assert seconds(tutorial) == 10, "no second counted twice"


def test_leaving_without_standing_loses_up_to_ten_seconds(tutorial: Engine) -> None:
    # The article's worst case: variables cannot change when a user leaves the room.
    sit(tutorial)
    tutorial.advance(19 * SECOND)
    assert seconds(tutorial) == 10
    tutorial.apply_input({"type": "leave", "user": AVATAR})
    assert seconds(tutorial) == 10, "the last 9 seconds are lost"
    tutorial.advance(60 * SECOND)
    assert seconds(tutorial) == 10


def test_clock_does_not_drift_over_a_long_shift(tutorial: Engine) -> None:
    sit(tutorial)
    for _ in range(60):
        tutorial.advance(61 * SECOND)
    tutorial.apply_input({"type": "say", "user": AVATAR, "text": KEYWORD})
    assert seconds(tutorial) == 3660


def test_two_shifts_add_up(tutorial: Engine) -> None:
    sit(tutorial)
    tutorial.advance(5 * SECOND)
    stand(tutorial)
    tutorial.advance(30 * SECOND)
    sit(tutorial)
    tutorial.advance(6 * SECOND)
    stand(tutorial)
    assert seconds(tutorial) == 11


def test_replay_gives_the_same_result(tutorial: Engine) -> None:
    sit(tutorial)
    tutorial.advance(14 * SECOND)
    tutorial.apply_input({"type": "say", "user": AVATAR, "text": KEYWORD})
    stand(tutorial)
    tutorial.advance(5 * SECOND)
    again = replay(time_tracking(), tutorial.seed, tutorial.inputs, tutorial.now_ms)
    assert again.snapshot() == tutorial.snapshot()
    assert again.trace == tutorial.trace


# --- Helpers for small rooms ---


def box(id_: int, classname: str, x: int, y: int, z: float = 0, **settings: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "classname": classname,
        "x": x,
        "y": y,
        "z": z,
        "rot": 0,
        "state": 0,
        "wired": settings,
    }


def plain(id_: int, classname: str = "chair", x: int = 9, y: int = 9) -> dict[str, Any]:
    return {"id": id_, "classname": classname, "x": x, "y": y, "z": 0, "rot": 0, "state": 0}


def user(id_: int = 100, name: str = "Ann", x: int = 0, y: int = 9) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "hotel": "com",
        "figure": "hd-1",
        "x": x,
        "y": y,
        "z": 0,
        "dir": 2,
        "pose": "std",
    }


def room(*furni: dict[str, Any], users: list[dict[str, Any]] | None = None, seed: int = 1) -> Engine:
    document = {"schema": 1, "room": {"width": 20, "height": 20}, "furni": list(furni)}
    document["avatars"] = users if users is not None else [user()]
    return Engine(document, seed=seed)


def logs(engine: Engine) -> list[str]:
    return [e["message"] for e in engine.trace if e["kind"] == "log"]


def say(engine: Engine, text: str, who: int = 100) -> None:
    engine.apply_input({"type": "say", "user": who, "text": text})


def test_keyword_matching() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="hello"),
        box(2, "wf_act_log", 1, 1, 1, text="partial"),
        box(3, "wf_trg_says_something", 2, 1, text="hello", exact=True),
        box(4, "wf_act_log", 2, 1, 1, text="exact"),
    )
    say(engine, "HELLO there")
    assert logs(engine) == ["partial"]
    say(engine, " hello ")
    assert sorted(logs(engine)) == ["exact", "partial", "partial"]


def test_conditions_block_and_or_eval_relaxes() -> None:
    def stack(*extra: dict[str, Any]) -> Engine:
        return room(
            box(1, "wf_trg_says_something", 1, 1, text="go"),
            box(2, "wf_cnd_user_count_in", 1, 1, 1, min=5, max=9),
            box(3, "wf_cnd_user_count_in", 1, 1, 2, min=1, max=2),
            box(4, "wf_act_log", 1, 1, 3, text="ran"),
            *extra,
        )

    engine = stack()
    say(engine, "go")
    assert logs(engine) == []
    engine = stack(box(5, "wf_xtra_or_eval", 1, 1, 4))
    say(engine, "go")
    assert logs(engine) == ["ran"]


def test_delay_counts_half_seconds() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_log", 1, 1, 1, text="later", delay=4),
    )
    say(engine, "go")
    engine.advance(1999)
    assert logs(engine) == []
    engine.advance(1)
    assert logs(engine) == ["later"]


def test_execute_in_order_runs_top_down_and_default_order_varies() -> None:
    boxes = [box(i, "wf_act_log", 1, 1, i, text=str(i)) for i in range(2, 8)]
    trigger = box(1, "wf_trg_says_something", 1, 1, text="go")
    engine = room(trigger, *boxes, box(20, "wf_xtra_exec_in_order", 1, 1, 9))
    say(engine, "go")
    assert logs(engine) == ["7", "6", "5", "4", "3", "2"]
    orders = set()
    for seed in range(8):
        engine = room(trigger, *boxes, seed=seed)
        say(engine, "go")
        orders.add(tuple(logs(engine)))
    assert len(orders) > 1, "unordered stacks must not look reliably ordered"


def test_random_and_unseen_addons() -> None:
    boxes = [box(i, "wf_act_log", 1, 1, i, text=str(i)) for i in range(2, 5)]
    trigger = box(1, "wf_trg_says_something", 1, 1, text="go")
    engine = room(trigger, *boxes, box(20, "wf_xtra_random", 1, 1, 9))
    say(engine, "go")
    assert len(logs(engine)) == 1
    engine = room(trigger, *boxes, box(20, "wf_xtra_unseen", 1, 1, 9))
    for _ in range(3):
        say(engine, "go")
    assert sorted(logs(engine)) == ["2", "3", "4"], "each once before any repeats"


def test_same_seed_same_random() -> None:
    def run(seed: int) -> list[str]:
        boxes = [box(i, "wf_act_log", 1, 1, i, text=str(i)) for i in range(2, 9)]
        engine = room(
            box(1, "wf_trg_periodically", 1, 1, seconds=1),
            *boxes,
            box(20, "wf_xtra_random", 1, 1, 9),
            seed=seed,
        )
        engine.advance(10_000)
        return logs(engine)

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_selectors_and_filters() -> None:
    users = [user(100, "Ann"), user(101, "Bob", x=1), user(102, "Cy", x=2)]
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann\nBob"),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", value=1),
        users=users,
    )
    say(engine, "go")
    assert set(engine.variables["v"]) == {"user:100", "user:101"}

    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann\nbob\ncy"),
        box(3, "wf_xtra_filter_users", 1, 1, 2, amount=1),
        box(4, "wf_act_give_var", 1, 1, 3, variable="v"),
        users=users,
    )
    say(engine, "go")
    assert len(engine.variables["v"]) == 1


def test_selector_with_no_match_affects_nobody_not_the_triggerer() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_with_var", 1, 1, 1, variable="nope"),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v"),
    )
    say(engine, "go")
    assert engine.variables["v"] == {}


def test_give_without_overwrite_keeps_value_and_timestamp() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_give_var", 1, 1, 1, variable="v", value=5),
    )
    say(engine, "go")
    engine.advance(1000)
    say(engine, "go")
    assert engine.variables["v"]["user:100"].created_ms == 0


def test_changing_a_variable_nobody_has_is_reported_not_created() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_change_var_val", 1, 1, 1, variable="v", operation="add", value=1),
    )
    say(engine, "go")
    assert engine.variables["v"] == {}
    assert any(e["kind"] == "error" for e in engine.trace)


def test_arithmetic_edges() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_give_var", 1, 1, 9, variable="v", value=INT64_MAX),
        box(3, "wf_act_change_var_val", 1, 1, 8, variable="v", operation="multiply", value=4),
        box(4, "wf_act_change_var_val", 1, 1, 7, variable="v", operation="divide", value=0),
        box(5, "wf_xtra_exec_in_order", 1, 1, 10),
    )
    say(engine, "go")
    assert engine.variables["v"]["user:100"].value == INT64_MAX


def test_global_variables_have_one_value() -> None:
    engine = room(
        box(1, "wf_var_room", 0, 0, variable="g"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_act_give_var", 1, 1, 1, variable="g", value=3),
    )
    say(engine, "go")
    assert set(engine.variables["g"]) == {"global"}


def test_context_variables_last_one_run() -> None:
    engine = room(
        box(1, "wf_var_context", 0, 0, variable="c"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_act_give_var", 1, 1, 9, variable="c", value=3),
        box(4, "wf_act_log", 1, 1, 8, text="$(n)"),
        box(5, "wf_xtra_text_output_variable", 1, 1, 10, placeholder="n", variable="c"),
        box(6, "wf_xtra_exec_in_order", 1, 1, 11),
    )
    say(engine, "go")
    assert logs(engine) == ["3"]
    assert engine.variables["c"] == {}


def test_placeholders_and_text_connector() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_give_var", 1, 1, 9, variable="item", value=3),
        box(3, "wf_act_show_message", 1, 1, 8, text="$(user) has $(thing) $(unknown)"),
        box(4, "wf_xtra_text_output_username", 1, 1, 10, placeholder="user"),
        box(5, "wf_xtra_text_output_variable", 1, 1, 11, placeholder="thing", variable="item"),
        box(6, "wf_xtra_var_text_connector", 1, 1, 12, variable="item", mapping="3=carrot\n4=pear"),
        box(7, "wf_xtra_exec_in_order", 1, 1, 13),
    )
    say(engine, "go")
    assert engine.messages[0]["text"] == "Ann has carrot $(unknown)"


def test_furni_triggers_only_fire_for_their_picks() -> None:
    engine = room(
        plain(50, x=3, y=3),
        plain(51, x=4, y=3),
        box(1, "wf_trg_walks_on_furni", 1, 1, furni=[50]),
        box(2, "wf_act_log", 1, 1, 1, text="on"),
        box(3, "wf_trg_walks_off_furni", 2, 1, furni=[50]),
        box(4, "wf_act_log", 2, 1, 1, text="off"),
        box(5, "wf_trg_click_furni", 3, 1, furni=[51]),
        box(6, "wf_act_log", 3, 1, 1, text="clicked"),
    )
    move = {"type": "move", "user": 100}
    engine.apply_input({**move, "x": 4, "y": 3})
    assert logs(engine) == []
    engine.apply_input({**move, "x": 3, "y": 3})
    assert logs(engine) == ["on"]
    engine.apply_input({**move, "x": 3, "y": 4})
    assert logs(engine) == ["on", "off"]
    engine.apply_input({"type": "click", "user": 100, "furni": 50})
    assert len(logs(engine)) == 2
    engine.apply_input({"type": "click", "user": 100, "furni": 51})
    assert logs(engine)[-1] == "clicked"


def test_toggle_state_and_state_trigger() -> None:
    engine = room(
        plain(50),
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_toggle_state", 1, 1, 1, furni=[50]),
        box(3, "wf_trg_stuff_state", 2, 1, furni=[50]),
        box(4, "wf_act_log", 2, 1, 1, text="changed"),
    )
    say(engine, "go")
    assert engine.furni[50]["state"] == 1
    assert logs(engine) == ["changed"]


def test_teleport_and_move() -> None:
    engine = room(
        plain(50, x=5, y=6),
        box(1, "wf_trg_says_something", 1, 1, text="tp"),
        box(2, "wf_act_teleport_to", 1, 1, 1, furni=[50]),
        box(3, "wf_trg_says_something", 2, 1, text="mv"),
        box(4, "wf_act_move_rotate", 2, 1, 1, furni=[50], direction="x+", rotation="clockwise"),
    )
    say(engine, "tp")
    assert (engine.users[100]["x"], engine.users[100]["y"]) == (5, 6)
    say(engine, "mv")
    assert (engine.furni[50]["x"], engine.furni[50]["rot"]) == (6, 2)


def test_call_stacks_ignores_conditions_and_trigger() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_call_stacks", 1, 1, 1, furni=[3]),
        box(3, "wf_trg_says_something", 2, 1, text="never"),
        box(4, "wf_cnd_user_count_in", 2, 1, 1, min=9, max=9),
        box(5, "wf_act_log", 2, 1, 2, text="called"),
    )
    say(engine, "go")
    assert logs(engine) == ["called"]


def test_timer_triggers_and_conditions() -> None:
    engine = room(
        box(1, "wf_trg_at_given_time", 1, 1, seconds=2),
        box(2, "wf_act_log", 1, 1, 1, text="timer"),
        box(3, "wf_trg_says_something", 2, 1, text="reset"),
        box(4, "wf_act_reset_timers", 2, 1, 1),
        box(5, "wf_trg_says_something", 3, 1, text="early"),
        box(6, "wf_cnd_time_less_than", 3, 1, 1, seconds=1),
        box(7, "wf_act_log", 3, 1, 2, text="early"),
    )
    say(engine, "early")
    assert logs(engine) == ["early"]
    engine.advance(2000)
    assert logs(engine) == ["early", "timer"]
    engine.advance(5000)
    assert logs(engine) == ["early", "timer"], "fires once per reset"
    say(engine, "early")
    assert len(logs(engine)) == 2
    say(engine, "reset")
    engine.advance(2000)
    assert logs(engine)[-1] == "timer"
    assert len(logs(engine)) == 3


def test_signal_loop_stops_at_the_limit() -> None:
    engine = room(
        plain(50),
        box(1, "wf_trg_recv_signal", 1, 1, antenna=[50]),
        box(2, "wf_act_send_signal", 1, 1, 1, antenna=[50]),
        box(3, "wf_trg_says_something", 2, 1, text="go"),
        box(4, "wf_act_send_signal", 2, 1, 1, antenna=[50]),
    )
    say(engine, "go")
    assert engine.limit_hits == 1
    assert any(e["kind"] == "limit" for e in engine.trace)


def test_execution_limit_addon() -> None:
    engine = room(
        box(1, "wf_trg_periodically", 1, 1, seconds=1),
        box(2, "wf_act_log", 1, 1, 1, text="run"),
        box(3, "wf_xtra_execution_limit", 1, 1, 2, count=2, window_seconds=5),
    )
    engine.advance(5000)
    assert len(logs(engine)) == 2
    assert engine.limit_hits == 3


def test_furious_room_cannot_hang_the_server() -> None:
    boxes = [box(i, "wf_trg_periodically", i, 0, seconds=0) for i in range(1, 40)]
    boxes += [box(i + 100, "wf_act_log", i, 0, 1, text="x") for i in range(1, 40)]
    engine = room(*boxes)
    engine.advance(10 * 60 * 1000)
    assert engine.now_ms == 10 * 60 * 1000


def test_trace_is_capped() -> None:
    engine = room(box(1, "wf_trg_periodically", 1, 1, seconds=1), box(2, "wf_act_log", 1, 1, 1, text="x"))
    engine.advance(10 * 60 * 1000)
    engine.advance(10 * 60 * 1000)
    engine.advance(10 * 60 * 1000)
    assert len(engine.trace) <= 4000


def test_unknown_boxes_are_stubs_and_are_logged() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_give_reward", 1, 1, 1),
        box(3, "wf_test_cnd", 1, 1, 2),
        box(4, "wf_act_log", 1, 1, 3, text="still ran"),
    )
    say(engine, "go")
    assert logs(engine) == ["still ran"]
    stubs = [e["message"] for e in engine.trace if e["kind"] == "stub"]
    assert any("act_give_reward" in s for s in stubs)
    assert any("test_cnd" in s for s in stubs)


@pytest.mark.parametrize(
    "settings",
    [
        {"seconds": "soon"},
        {"seconds": None},
        {"furni": "all"},
        {"furni": [None, "x", 9999]},
        {"variable": {"a": 1}},
        {"value": [1]},
        {"delay": "x"},
        {"antenna": 5},
        {"amount": "many"},
        {"text": 12},
        {"mapping": []},
    ],
)
def test_bad_settings_never_raise(settings: dict[str, Any]) -> None:
    names = [
        "wf_trg_periodically",
        "wf_slc_furni_picks",
        "wf_act_give_var",
        "wf_act_change_var_val",
        "wf_act_send_signal",
        "wf_act_toggle_state",
        "wf_act_move_rotate",
        "wf_act_show_message",
        "wf_xtra_filter_users",
        "wf_xtra_var_text_connector",
        "wf_cnd_trggrer_on_frn",
    ]
    furni = [box(1, "wf_trg_says_something", 1, 1, text="go")]
    furni += [box(i + 2, name, 1, 1, i + 1, **settings) for i, name in enumerate(names)]
    engine = room(*furni)
    say(engine, "go")
    engine.advance(5000)


def test_unknown_input_and_people_are_ignored() -> None:
    engine = room()
    for entry in (
        {"type": "nonsense"},
        {"type": "move", "user": 999, "x": 1, "y": 1},
        {"type": "say", "user": 999, "text": "x"},
        {"type": "use", "user": 100, "furni": 999},
    ):
        engine.apply_input(entry)


def test_antenna_constant_is_a_real_furni() -> None:
    assert any(f["id"] == ANTENNA_CALC for f in time_tracking()["furni"])
    assert any(f["id"] == SEAT for f in time_tracking()["furni"])


def state_room() -> dict[str, Any]:
    return {
        "furni": [{"id": 1, "classname": "wf_floor_switch1", "x": 1, "y": 1}],
        "avatars": [{"id": 2, "name": "A", "x": 2, "y": 2}],
    }


def uses(engine: Engine, count: int) -> list[int]:
    seen = []
    for _ in range(count):
        engine.apply_input({"type": "use", "user": 2, "furni": 1})
        seen.append(engine.furni[1]["state"])
    return seen


def test_using_furni_loops_through_its_states() -> None:
    assert uses(Engine(state_room()), 5) == [1, 0, 1, 0, 1], "two states when the art is unknown"
    three = Engine(state_room(), furni_states={"wf_floor_switch1": [0, 1, 2]})
    assert uses(three, 4) == [1, 2, 0, 1]
    assert uses(Engine(state_room(), furni_states={"wf_floor_switch1": [0]}), 2) == [0, 0]
    gaps = Engine(state_room(), furni_states={"wf_floor_switch1": [0, 5]})
    assert uses(gaps, 3) == [5, 0, 5]


def test_a_state_the_furni_lacks_returns_to_its_first() -> None:
    document = state_room()
    document["furni"][0]["state"] = 9
    assert uses(Engine(document), 1) == [0]


def says_engine(**settings: Any) -> Engine:
    return Engine(
        {
            "furni": [
                box(1, "wf_trg_says_something", 1, 1, text="hello there", **settings),
                box(2, "wf_act_log", 1, 1, 1, text="ran"),
            ],
            "avatars": [{"id": 9, "name": "A", "x": 2, "y": 2}],
        }
    )


@pytest.mark.parametrize(
    ("settings", "said", "runs"),
    [
        ({}, "oh hello there you", True),
        ({"match": "contains"}, "shello therefore", True),
        ({"match": "exact"}, "oh hello there you", True),
        ({"match": "exact"}, "shello therefore", False),
        ({"match": "all"}, "oh hello there you", False),
        ({"match": "all"}, "Hello There", True),
        ({"exact": True}, "oh hello there you", False),
    ],
)
def test_keyword_types(settings: dict[str, Any], said: str, runs: bool) -> None:
    engine = says_engine(**settings)
    engine.apply_input({"type": "say", "user": 9, "text": said})
    assert bool(logs(engine)) is runs
