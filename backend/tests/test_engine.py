from __future__ import annotations

from typing import Any

import pytest

from wiredbench.engine.core import INT64_MAX, Context, Engine, replay
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


def test_variable_value_condition_defaults_to_greater_than() -> None:
    engine = room(
        box(1, "wf_var_room", 5, 5, variable="round"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_cnd_var_val_match", 1, 1, 1, variable="round", value=5),
        box(4, "wf_act_log", 1, 1, 2, text="ran"),
    )
    engine.apply_input({"type": "api_set", "variable": "round", "key": "global", "value": 5})
    say(engine, "go")
    engine.advance(1)
    assert logs(engine) == []
    engine.apply_input({"type": "api_set", "variable": "round", "key": "global", "value": 6})
    say(engine, "go")
    engine.advance(1)
    assert logs(engine) == ["ran"]


def test_short_period_runs_at_its_own_speed_and_stops_at_a_minimum() -> None:
    for seconds, runs in ((0.35, 8), (0, 60)):
        engine = room(
            box(1, "wf_trg_period_short", 1, 1, seconds=seconds),
            box(2, "wf_act_log", 1, 1, 1, text="x"),
        )
        engine.advance(3000)
        assert len(logs(engine)) == runs


def test_defined_variables_are_listed_until_something_holds_them() -> None:
    engine = room(
        box(1, "wf_var_user", 2, 2, variable="score"),
        box(2, "wf_var_context", 3, 3, variable="temp"),
    )
    assert engine.view_defined() == [
        {"variable": "score", "scope": "user"},
        {"variable": "temp", "scope": "context"},
    ]
    engine.apply_input({"type": "api_set", "variable": "score", "key": "user:1", "value": 5})
    assert [row["variable"] for row in engine.view_defined()] == ["temp"]
    assert engine.snapshot()["defined_variables"] == engine.view_defined()


def test_a_global_reads_zero_before_anything_sets_it() -> None:
    engine = room(
        box(1, "wf_var_room", 5, 5, variable="round"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_act_change_var_val", 1, 1, 1, variable="round", operation="add", value=2),
    )
    assert [(r["variable"], r["holder"], r["value"]) for r in engine.view_variables()] == [
        ("round", "global", "0")
    ]
    assert engine.view_defined() == []
    say(engine, "go")
    assert engine.variables["round"]["global"].value == 2


@pytest.mark.parametrize(
    ("settings", "wait", "passes"),
    [
        ({"compare": "less", "duration": 2, "unit": "seconds"}, 1000, True),
        ({"compare": "less", "duration": 2, "unit": "seconds"}, 2000, False),
        ({"compare": "equal", "duration": 2, "unit": "seconds"}, 2000, True),
        ({"compare": "more", "duration": 2, "unit": "seconds"}, 2001, True),
        ({"compare": "more", "duration": 1, "unit": "minutes"}, 59_000, False),
        ({"compare": "less", "duration": 500, "unit": "milliseconds"}, 499, True),
    ],
)
def test_variable_age(settings: dict[str, Any], wait: int, passes: bool) -> None:
    engine = room(
        box(1, "wf_var_user", 5, 5, variable="role"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_cnd_var_age_match", 1, 1, 1, variable="role", **settings),
        box(4, "wf_act_log", 1, 1, 2, text="ran"),
    )
    engine.apply_input({"type": "api_set", "variable": "role", "key": "user:100", "value": 1})
    engine.advance(wait)
    say(engine, "go")
    assert logs(engine) == (["ran"] if passes else [])


def test_variable_age_can_measure_from_the_last_change() -> None:
    def ran(age_of: str) -> list[str]:
        engine = room(
            box(1, "wf_var_user", 5, 5, variable="role"),
            box(2, "wf_trg_says_something", 1, 1, text="go"),
            box(
                3,
                "wf_cnd_var_age_match",
                1,
                1,
                1,
                variable="role",
                compare="less",
                duration=1,
                age_of=age_of,
            ),
            box(4, "wf_act_log", 1, 1, 2, text="ran"),
        )
        engine.apply_input({"type": "api_set", "variable": "role", "key": "user:100", "value": 1})
        engine.advance(5000)
        engine.apply_input({"type": "api_set", "variable": "role", "key": "user:100", "value": 2})
        say(engine, "go")
        return logs(engine)

    assert ran("update") == ["ran"]
    assert ran("creation") == []


def test_variable_age_fails_when_nothing_holds_the_variable() -> None:
    engine = room(
        box(1, "wf_var_user", 5, 5, variable="role"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_cnd_var_age_match", 1, 1, 1, variable="role", compare="more"),
        box(4, "wf_act_log", 1, 1, 2, text="ran"),
    )
    say(engine, "go")
    assert logs(engine) == []


def test_value_can_come_from_another_variable() -> None:
    engine = room(
        box(1, "wf_var_user", 5, 5, variable="base"),
        box(2, "wf_var_user", 6, 6, variable="copy"),
        box(3, "wf_var_room", 7, 7, variable="limit"),
        box(4, "wf_trg_says_something", 1, 1, text="go"),
        box(5, "wf_xtra_exec_in_order", 1, 1, 9),
        box(6, "wf_act_give_var", 1, 1, 8, variable="copy", from_variable="base", value=1),
        box(7, "wf_act_log", 1, 1, 7, text="ran"),
        box(8, "wf_trg_says_something", 2, 2, text="check"),
        box(9, "wf_cnd_var_val_match", 2, 2, 1, variable="copy", compare=">", from_variable="limit"),
        box(10, "wf_act_log", 2, 2, 2, text="passed"),
    )
    engine.apply_input({"type": "api_set", "variable": "base", "key": "user:100", "value": 9})
    engine.apply_input({"type": "api_set", "variable": "limit", "key": "global", "value": 5})
    say(engine, "go")
    assert engine.variables["copy"]["user:100"].value == 9
    say(engine, "check")
    assert "passed" in logs(engine)
    engine.apply_input({"type": "api_set", "variable": "limit", "key": "global", "value": 50})
    say(engine, "check")
    assert logs(engine).count("passed") == 1


def test_give_variable_gives_nothing_when_its_source_is_empty() -> None:
    engine = room(
        box(1, "wf_var_user", 5, 5, variable="base"),
        box(2, "wf_var_user", 6, 6, variable="copy"),
        box(3, "wf_trg_says_something", 1, 1, text="go"),
        box(4, "wf_act_give_var", 1, 1, 1, variable="copy", from_variable="base", value=1),
    )
    say(engine, "go")
    assert "user:100" not in engine.variables["copy"]


def test_furni_variables_are_given_to_picked_furni() -> None:
    engine = room(
        box(1, "wf_var_furni", 5, 5, variable="mark"),
        box(9, "wf_var_user", 6, 6, variable="plain"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_act_give_var", 1, 1, 1, variable="mark", value=4, furni=[9]),
    )
    say(engine, "go")
    assert engine.variables["mark"]["furni:9"].value == 4
    assert "furni:100" not in engine.variables["mark"]


def test_conditions_and_removal_follow_a_furni_variable() -> None:
    engine = room(
        box(1, "wf_var_furni", 5, 5, variable="mark"),
        box(9, "wf_var_user", 6, 6, variable="plain"),
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_cnd_has_var", 1, 1, 1, variable="mark", furni=[9]),
        box(4, "wf_act_log", 1, 1, 2, text="held"),
        box(5, "wf_trg_says_something", 2, 2, text="clear"),
        box(6, "wf_act_remove_var", 2, 2, 1, variable="mark", furni=[9]),
    )
    say(engine, "go")
    assert logs(engine) == []
    engine.apply_input({"type": "api_set", "variable": "mark", "key": "furni:9", "value": 1})
    say(engine, "go")
    assert logs(engine) == ["held"]
    say(engine, "clear")
    assert "furni:9" not in engine.variables["mark"]


def test_a_global_change_needs_no_user() -> None:
    engine = room(
        box(1, "wf_var_room", 5, 5, variable="round"),
        box(2, "wf_trg_periodically", 1, 1, seconds=1),
        box(3, "wf_act_change_var_val", 1, 1, 1, variable="round", operation="add", value=1),
    )
    engine.advance(1000)
    assert engine.variables["round"]["global"].value == 1


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


@pytest.mark.parametrize(("delay", "wait"), [(-650, 650), (-50, 50), (-90000, 60000), (900, 300000)])
def test_negative_delays_are_milliseconds_and_all_delays_are_capped(delay: int, wait: int) -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_log", 1, 1, 1, text="later", delay=delay),
    )
    say(engine, "go")
    engine.advance(wait - 1)
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
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", value=1, user_source="selector"),
        users=users,
    )
    say(engine, "go")
    assert set(engine.variables["v"]) == {"user:100", "user:101"}

    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann\nbob\ncy"),
        box(3, "wf_xtra_filter_users", 1, 1, 2, amount=1),
        box(4, "wf_act_give_var", 1, 1, 3, variable="v", user_source="selector"),
        users=users,
    )
    say(engine, "go")
    assert len(engine.variables["v"]) == 1


def holders(engine: Engine) -> set[str]:
    return set(engine.variables["v"])


def test_selectors_add_up_and_filters_narrow_wherever_they_stand() -> None:
    users = [user(100, "Ann"), user(101, "Bob", x=1), user(102, "Cy", x=2)]
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann"),
        box(3, "wf_slc_users_byname", 1, 1, 2, names="bob"),
        box(4, "wf_act_give_var", 1, 1, 3, variable="v", user_source="selector"),
        users=users,
    )
    say(engine, "go")
    assert holders(engine) == {"user:100", "user:101"}

    for filter_height, pick_height in ((1, 2), (2, 1)):
        engine = room(
            box(1, "wf_trg_says_something", 1, 1, text="go"),
            box(2, "wf_slc_users_byname", 1, 1, filter_height, names="bob\ncy", filter=True),
            box(3, "wf_slc_users_byname", 1, 1, pick_height, names="ann\nbob"),
            box(4, "wf_act_give_var", 1, 1, 3, variable="v", user_source="selector"),
            users=users,
        )
        say(engine, "go")
        assert holders(engine) == {"user:101"}


def test_a_filter_alone_selects_nobody() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann", filter=True),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", user_source="selector"),
    )
    say(engine, "go")
    assert holders(engine) == set()


def test_invert_selects_what_did_not_match() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_byname", 1, 1, 1, names="ann", invert=True),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", user_source="selector"),
        users=[user(100, "Ann"), user(101, "Bob", x=1)],
    )
    say(engine, "go")
    assert holders(engine) == {"user:101"}


def test_area_selectors_cover_their_rectangle() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_area", 1, 1, 1, area_x=2, area_y=3, area_width=2, area_height=1),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", user_source="selector"),
        users=[
            user(100, "Ann", x=2, y=3),
            user(101, "Bob", x=3, y=3),
            user(102, "Cy", x=4, y=3),
            user(103, "Di", x=2, y=4),
        ],
    )
    say(engine, "go")
    assert holders(engine) == {"user:100", "user:101"}


def selected_furni(*selectors: dict[str, Any], extra: tuple[dict[str, Any], ...] = ()) -> list[int] | None:
    engine = room(box(1, "wf_trg_says_something", 1, 1, text="go"), *selectors, *extra)
    stack = engine.stacks[0]
    ctx = Context()
    engine._apply_selectors(stack, ctx)
    return ctx.selected_furni


def test_furni_area_and_altitude() -> None:
    inside = box(10, "lamp", 5, 5, 0.5)
    outside = box(11, "lamp", 6, 5, 2)
    assert selected_furni(
        box(2, "wf_slc_furni_area", 1, 1, 1, area_x=5, area_y=5, area_width=1, area_height=1),
        extra=(inside, outside),
    ) == [10]
    for compare, expected in (("less", [10]), ("equal", [11]), ("more", [])):
        found = selected_furni(
            box(2, "wf_slc_furni_altitude", 1, 1, 1, altitude=2, altitude_compare=compare, filter=False),
            extra=(inside, outside),
        )
        assert [i for i in found or [] if i >= 10] == expected


def test_furni_on_furni_follows_the_pile() -> None:
    pile = (box(10, "a", 5, 5, 0), box(11, "b", 5, 5, 1), box(12, "c", 5, 5, 2), box(13, "d", 6, 5, 2))
    for stacking, expected in (
        ("above", [12]),
        ("below", [10]),
        ("level", [11]),
        ("tile", [10, 11, 12]),
    ):
        assert (
            selected_furni(box(2, "wf_slc_furni_onfurni", 1, 1, 1, furni=[11], stacking=stacking), extra=pile)
            == expected
        )


def test_selector_with_no_match_affects_nobody_not_the_triggerer() -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_with_var", 1, 1, 1, variable="nope"),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v", user_source="selector"),
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
        ({"match": "exact"}, "oh hello there you", False),
        ({"match": "exact"}, "Hello There", True),
        ({"match": "all"}, "something else entirely", True),
        ({"exact": True}, "oh hello there you", False),
        ({"exact": True}, "hello there", True),
    ],
)
def test_keyword_types(settings: dict[str, Any], said: str, runs: bool) -> None:
    engine = says_engine(**settings)
    engine.apply_input({"type": "say", "user": 9, "text": said})
    assert bool(logs(engine)) is runs


def test_periods_and_limit_windows_can_be_half_seconds() -> None:
    engine = Engine(
        {
            "furni": [
                box(1, "wf_trg_periodically", 1, 1, seconds=2.5),
                box(2, "wf_act_log", 1, 1, 1, text="ran"),
            ]
        }
    )
    engine.advance(2000)
    assert logs(engine) == []
    engine.advance(500)
    assert logs(engine) == ["ran"]


def test_random_rotation_turns_furni_and_replays() -> None:
    def run(seed: int) -> list[int]:
        engine = Engine(
            {
                "furni": [
                    {"id": 1, "classname": "chair", "x": 3, "y": 3},
                    box(2, "wf_trg_periodically", 1, 1, seconds=1),
                    box(3, "wf_act_move_rotate", 1, 1, 1, furni=[1], rotation="random"),
                ]
            },
            seed=seed,
        )
        seen = []
        for _ in range(8):
            engine.advance(1000)
            seen.append(engine.furni[1]["rot"])
        return seen

    assert run(4) == run(4)
    assert len(set(run(4))) > 1
    assert set(run(4)) <= {0, 2, 4, 6}


def moved(
    effect: dict[str, Any], *extra: dict[str, Any], users: list[dict[str, Any]] | None = None
) -> Engine:
    engine = room(box(1, "wf_trg_says_something", 1, 1, text="go"), effect, *extra, users=users)
    say(engine, "go", users[0]["id"] if users else 100)
    engine.advance(1000)
    return engine


def test_relative_move_stops_at_the_edge_and_at_users() -> None:
    lamp = box(50, "lamp", 5, 5)
    engine = moved(box(2, "wf_act_rel_mov", 1, 1, 1, furni=[50], move_x=3, move_y=-2), lamp)
    assert (engine.furni[50]["x"], engine.furni[50]["y"]) == (8, 3)
    engine = moved(box(2, "wf_act_rel_mov", 1, 1, 1, furni=[50], move_x=-9), lamp)
    assert engine.furni[50]["x"] == 5, "off the room"
    engine = moved(
        box(2, "wf_act_rel_mov", 1, 1, 1, furni=[50], move_x=1), lamp, users=[user(100, "Ann", 6, 5)]
    )
    assert engine.furni[50]["x"] == 5, "a user is in the way"


def test_move_rotate_takes_diagonals() -> None:
    engine = moved(box(2, "wf_act_move_rotate", 1, 1, 1, furni=[50], direction="x+y-"), box(50, "lamp", 5, 5))
    assert (engine.furni[50]["x"], engine.furni[50]["y"]) == (6, 4)


@pytest.mark.parametrize(("change", "expected"), [("raise", 2.5), ("lower", 0.5), ("set", 1.0)])
def test_set_altitude(change: str, expected: float) -> None:
    effect = box(2, "wf_act_set_altitude", 1, 1, 1, furni=[50], altitude=1, altitude_change=change)
    assert moved(effect, box(50, "lamp", 5, 5, 1.5)).furni[50]["z"] == expected


def test_altitude_stays_within_the_room() -> None:
    effect = box(2, "wf_act_set_altitude", 1, 1, 1, furni=[50], altitude=80)
    assert moved(effect, box(50, "lamp", 5, 5, 1)).furni[50]["z"] == 80


def test_bad_altitude_settings_never_raise() -> None:
    effect = box(2, "wf_act_set_altitude", 1, 1, 1, furni=[50], altitude=[], altitude_change=[])
    assert moved(effect, box(50, "lamp", 5, 5, 1)).furni[50]["z"] == 1


def test_furni_to_user_uses_the_first_user() -> None:
    engine = moved(
        box(2, "wf_act_furni_to_user", 1, 1, 1, furni=[50]),
        box(50, "lamp", 5, 5),
        users=[user(100, "Ann", 7, 8)],
    )
    assert (engine.furni[50]["x"], engine.furni[50]["y"]) == (7, 8)


def test_furni_to_furni_moves_the_triggering_furni_onto_the_target() -> None:
    engine = room(
        box(1, "wf_trg_state_changed", 1, 1, furni=[50]),
        box(2, "wf_act_furni_to_furni", 1, 1, 1, furni=[51]),
        box(50, "ball", 5, 5),
        box(51, "spot", 9, 9),
    )
    engine._start(engine.stacks[0], Context(trigger=None, furni=50))
    engine.advance(1000)
    assert (engine.furni[50]["x"], engine.furni[50]["y"]) == (9, 9)


def test_move_user_walks_and_turns() -> None:
    effect = box(2, "wf_act_move_rotate_user", 1, 1, 1, user_move="x+", user_turn="clockwise")
    engine = moved(effect, users=[user(100, "Ann", 4, 4)])
    assert (engine.users[100]["x"], engine.users[100]["y"]) == (5, 4)
    assert engine.users[100]["dir"] == 3
    effect = box(2, "wf_act_move_rotate_user", 1, 1, 1, user_move="x-", user_turn="y+")
    engine = moved(effect, users=[user(100, "Ann", 0, 4)])
    assert engine.users[100]["x"] == 0, "off the room"
    assert engine.users[100]["dir"] == 4


def test_default_user_source_ignores_a_selector() -> None:
    corner = {"area_x": 0, "area_y": 0, "area_width": 1, "area_height": 1}
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_slc_users_area", 1, 1, 1, **corner),
        box(3, "wf_act_give_var", 1, 1, 2, variable="v"),
        box(4, "wf_act_give_var", 1, 1, 3, variable="w", user_source="selector"),
        users=[user(100, "Ann", 5, 5)],
    )
    say(engine, "go")
    engine.advance(1000)
    assert set(engine.variables["v"]) == {"user:100"}
    assert engine.variables["w"] == {}


def test_toggle_leaves_floor_switches_alone() -> None:
    engine = moved(
        box(2, "wf_act_toggle_state", 1, 1, 1, furni=[50, 51]),
        box(50, "wf_floor_switch1", 5, 5),
        box(51, "lamp", 6, 5),
    )
    assert engine.furni[50]["state"] == 0
    assert engine.furni[51]["state"] == 1


def test_turn_input_sets_direction() -> None:
    engine = room(users=[user(100, "Ann")])
    engine.apply_input({"type": "turn", "user": 100, "dir": 5})
    assert engine.users[100]["dir"] == 5


def team_room(*boxes: dict[str, Any]) -> Engine:
    return room(
        box(1, "wf_trg_says_something", 1, 1, text="join"),
        box(2, "wf_act_join_team", 1, 1, 1, team="blue"),
        box(3, "wf_trg_says_something", 2, 2, text="go"),
        *boxes,
    )


def test_join_and_leave_team() -> None:
    engine = team_room(box(4, "wf_act_leave_team", 2, 2, 1))
    say(engine, "join")
    engine.advance(1000)
    assert engine.users[100]["team"] == "blue"
    say(engine, "go")
    engine.advance(1000)
    assert engine.users[100]["team"] is None


@pytest.mark.parametrize(("team", "expected"), [("any", True), ("blue", True), ("red", False)])
def test_team_condition_and_selector(team: str, expected: bool) -> None:
    engine = team_room(
        box(4, "wf_cnd_actor_in_team", 2, 2, 1, team=team),
        box(5, "wf_act_give_var", 2, 2, 2, variable="v"),
    )
    say(engine, "go")
    engine.advance(1000)
    assert engine.variables["v"] == {}, "not in a team yet"
    say(engine, "join")
    engine.advance(1000)
    say(engine, "go")
    engine.advance(1000)
    assert bool(engine.variables["v"]) is expected

    engine = team_room(
        box(4, "wf_slc_users_team", 2, 2, 1, team=team),
        box(5, "wf_act_give_var", 2, 2, 2, variable="v", user_source="selector"),
    )
    say(engine, "join")
    engine.advance(1000)
    say(engine, "go")
    engine.advance(1000)
    assert bool(engine.variables["v"]) is expected


def test_points_only_count_during_a_game() -> None:
    engine = team_room(box(4, "wf_act_give_score", 2, 2, 1, points=5, times=2))
    say(engine, "join")
    engine.advance(1000)
    say(engine, "go")
    engine.advance(1000)
    assert engine.team_scores["blue"] == 0
    engine.apply_input({"type": "game_start"})
    for _ in range(3):
        say(engine, "go")
        engine.advance(1000)
    assert engine.team_scores["blue"] == 10, "the limit stops the third"
    engine.apply_input({"type": "game_end"})
    say(engine, "go")
    engine.advance(1000)
    assert engine.team_scores["blue"] == 10, "the score stays after the game"
    engine.apply_input({"type": "game_start"})
    assert engine.team_scores["blue"] == 0, "a new game starts from nothing"


def test_a_team_score_never_goes_below_zero() -> None:
    engine = team_room(box(4, "wf_act_give_score_tm", 2, 2, 1, points=-5, team="red"))
    engine.apply_input({"type": "game_start"})
    say(engine, "go")
    engine.advance(1000)
    assert engine.team_scores["red"] == 0


def test_game_triggers_fire() -> None:
    engine = room(
        box(1, "wf_trg_game_starts", 1, 1),
        box(2, "wf_act_give_var", 1, 1, 1, variable="started", user_source="selector"),
        box(3, "wf_slc_users_area", 1, 1, 2, area_x=0, area_y=0, area_width=64, area_height=64),
    )
    engine.apply_input({"type": "game_start"})
    engine.advance(1000)
    assert engine.variables["started"]


def clock_room(*boxes: dict[str, Any], classname: str = "wf_upcounter1") -> Engine:
    return room(box(50, classname, 9, 9), box(1, "wf_trg_says_something", 1, 1, text="go"), *boxes)


def control(command: str, z: float = 1, **settings: Any) -> dict[str, Any]:
    return box(2, "wf_act_control_clock", 1, 1, z, furni=[50], clock_control=command, **settings)


def test_a_counter_counts_up_in_half_seconds_and_shows_seconds() -> None:
    engine = clock_room(control("start"))
    say(engine, "go")
    engine.advance(3000)
    assert engine.clocks[50].half_seconds == 6
    assert engine.furni[50]["state"] == 3
    assert not engine.game_running, "a plain counter does not start a game"


def test_clock_commands() -> None:
    engine = clock_room(
        control("start"),
        box(3, "wf_trg_says_something", 2, 2, text="pause"),
        box(4, "wf_act_control_clock", 2, 2, 1, furni=[50], clock_control="pause"),
        box(5, "wf_trg_says_something", 3, 3, text="resume"),
        box(6, "wf_act_control_clock", 3, 3, 1, furni=[50], clock_control="resume"),
        box(7, "wf_trg_says_something", 4, 4, text="stop"),
        box(8, "wf_act_control_clock", 4, 4, 1, furni=[50], clock_control="stop"),
    )
    say(engine, "go")
    engine.advance(2000)
    say(engine, "pause")
    engine.advance(2000)
    assert engine.clocks[50].half_seconds == 4
    say(engine, "resume")
    engine.advance(1000)
    assert engine.clocks[50].half_seconds == 6
    say(engine, "stop")
    engine.advance(1000)
    assert engine.clocks[50].half_seconds == 6
    say(engine, "go")
    engine.advance(1000)
    assert engine.clocks[50].half_seconds == 2, "a stopped counter starts afresh"


def test_adjusting_does_not_fire_the_time_trigger_but_counting_does() -> None:
    engine = clock_room(
        box(2, "wf_act_adjust_clock", 1, 1, 1, furni=[50], clock_seconds=2, clock_change="set"),
        box(3, "wf_trg_says_something", 2, 2, text="run"),
        box(4, "wf_act_control_clock", 2, 2, 1, furni=[50]),
        box(5, "wf_trg_clock_counter", 3, 3, furni=[50], clock_seconds=2),
        box(6, "wf_act_show_message", 3, 3, 1, text="reached", user_source="trigger"),
        box(7, "wf_trg_clock_counter", 4, 4, furni=[50], clock_seconds=3),
        box(8, "wf_act_log", 4, 4, 1, text="three"),
    )
    say(engine, "go")
    engine.advance(1000)
    assert engine.clocks[50].half_seconds == 4
    assert engine.furni[50]["state"] == 2
    say(engine, "run")
    engine.advance(2000)
    assert engine.clocks[50].half_seconds == 8
    assert "three" in logs(engine)


def test_a_game_counter_runs_the_game() -> None:
    engine = clock_room(
        control("start"),
        box(3, "wf_trg_says_something", 2, 2, text="stop"),
        box(4, "wf_act_control_clock", 2, 2, 1, furni=[50], clock_control="stop"),
        box(5, "wf_trg_says_something", 3, 3, text="score"),
        box(6, "wf_act_give_score_tm", 3, 3, 1, points=9, team="red"),
        classname="wf_game_upcounter1",
    )
    say(engine, "go")
    engine.advance(1000)
    assert engine.game_running
    say(engine, "score")
    engine.advance(1000)
    assert engine.team_scores["red"] == 9
    say(engine, "stop")
    engine.advance(1000)
    assert not engine.game_running
    say(engine, "go")
    engine.advance(1000)
    assert engine.game_running
    assert engine.team_scores["red"] == 0, "a new game starts from nothing"


def test_a_game_timer_counts_down_and_ends_the_game() -> None:
    engine = room(box(50, "bb_counter", 9, 9, state=0))
    engine.furni[50]["state"] = 2
    engine.apply_input({"type": "use", "user": 100, "furni": 50})
    assert engine.game_running
    engine.advance(1000)
    assert engine.furni[50]["state"] == 1
    assert engine.game_running
    engine.advance(1000)
    assert engine.furni[50]["state"] == 0
    assert not engine.game_running


@pytest.mark.parametrize(
    ("compare", "points", "expected"), [("equal", 9, True), ("more", 9, False), ("less", 10, True)]
)
def test_team_has_score(compare: str, points: int, expected: bool) -> None:
    engine = room(
        box(1, "wf_trg_says_something", 1, 1, text="score"),
        box(2, "wf_act_give_score_tm", 1, 1, 1, points=9, team="red"),
        box(3, "wf_trg_says_something", 2, 2, text="check"),
        box(4, "wf_cnd_team_has_score", 2, 2, 1, team="red", points=points, score_compare=compare),
        box(5, "wf_act_give_var", 2, 2, 2, variable="v"),
    )
    engine.apply_input({"type": "game_start"})
    say(engine, "score")
    engine.advance(1000)
    say(engine, "check")
    engine.advance(1000)
    assert bool(engine.variables["v"]) is expected


def test_highlight_and_visibility_reach_furni_and_users() -> None:
    engine = moved(
        box(
            2,
            "wf_act_set_highlight",
            1,
            1,
            1,
            furni=[50],
            audience="everyone",
            highlight_type="tint",
            color=255,
        ),
        box(3, "wf_act_set_visibility", 1, 1, 2, furni=[50], audience="everyone", click_through=True),
        box(4, "wf_act_set_visibility", 1, 1, 3, target="users", audience="selected", user_source="trigger"),
        box(50, "lamp", 5, 5),
    )
    state = engine.snapshot()
    assert state["looks"]["furni"][50]["highlight"]["color"] == 255
    assert state["looks"]["furni"][50]["invisible"] is True
    assert state["looks"]["furni"][50]["click_through"] is True
    assert state["looks"]["users"][100]["invisible"] is True


def test_a_look_with_no_audience_does_nothing() -> None:
    engine = moved(
        box(2, "wf_act_set_visibility", 1, 1, 1, furni=[50], audience="selected", user_source="selector"),
        box(50, "lamp", 5, 5),
    )
    assert engine.snapshot()["looks"]["furni"] == {}


def test_carry_users_moves_who_stands_on_the_furni() -> None:
    effect = box(2, "wf_act_rel_mov", 1, 1, 1, furni=[50], move_x=2)
    carry = box(3, "wf_xtra_mov_carry_users", 1, 1, 2)
    lamp = box(50, "lamp", 5, 5)
    engine = moved(effect, carry, lamp, users=[user(100, "Ann", 5, 5), user(101, "Bob", 9, 9)])
    assert engine.furni[50]["x"] == 7
    assert (engine.users[100]["x"], engine.users[100]["y"]) == (7, 5)
    assert engine.users[101]["x"] == 9
    engine = moved(effect, lamp, users=[user(100, "Ann", 5, 5)])
    assert engine.users[100]["x"] == 5, "without the add-on the user stays"


def test_a_box_edited_during_a_run_uses_its_new_settings() -> None:
    engine = room(
        box(50, "wf_colortile", 5, 5),
        box(1, "wf_trg_says_something", 1, 1, text="go"),
        box(2, "wf_act_rel_mov", 1, 1, 1, furni=[50], move_x=1),
    )
    say(engine, "go")
    engine.advance(1000)
    assert engine.furni[50]["x"] == 6
    engine.apply_input({"type": "box_settings", "furni": 2, "settings": {"furni": [50], "move_y": 2}})
    say(engine, "go")
    engine.advance(1000)
    assert (engine.furni[50]["x"], engine.furni[50]["y"]) == (6, 7)


@pytest.mark.parametrize("settings", [None, "bad", 3, []])
def test_bad_box_edits_are_ignored(settings: Any) -> None:
    engine = room(box(1, "wf_trg_says_something", 1, 1, text="go"))
    engine.apply_input({"type": "box_settings", "furni": 1, "settings": settings})
    engine.apply_input({"type": "box_settings", "furni": 999, "settings": {}})
    say(engine, "go")


def fx_room(fx: dict[str, Any]) -> Engine:
    return room(
        box(1, "wf_var_user", 3, 3, variable="hp"),
        {**box(2, fx.pop("classname"), 3, 3, 1, **fx)},
        box(3, "wf_trg_says_something", 1, 1, text="go"),
        box(4, "wf_act_give_var", 1, 1, 1, variable="hp", value=40),
    )


def test_variable_fx_shows_the_variable_on_its_tile_over_each_holder() -> None:
    engine = fx_room({"classname": "wf_xtra_varfx_hp", "fx_max": 80})
    assert engine.snapshot()["fx"] == [], "nobody holds it yet"
    say(engine, "go")
    engine.advance(500)
    assert engine.snapshot()["fx"] == [
        {"kind": "hp", "target": "user", "id": 100, "value": "40", "min": 0, "max": 80, "order": 0}
    ]


def test_variable_fx_show_modes() -> None:
    engine = fx_room({"classname": "wf_xtra_varfx_number", "fx_show": "never"})
    say(engine, "go")
    engine.advance(500)
    assert engine.snapshot()["fx"] == []

    engine = fx_room({"classname": "wf_xtra_varfx_number", "fx_show": "changes", "fx_duration": 2000})
    say(engine, "go")
    engine.advance(500)
    assert len(engine.snapshot()["fx"]) == 1
    engine.advance(3000)
    assert engine.snapshot()["fx"] == []


def test_variable_fx_only_shows_over_its_kind_of_holder() -> None:
    engine = fx_room({"classname": "wf_xtra_varfx_number", "fx_target": "furni"})
    say(engine, "go")
    engine.advance(500)
    assert engine.snapshot()["fx"] == []


def test_a_variable_box_draws_at_most_five_fx() -> None:
    engine = room(
        box(1, "wf_var_user", 3, 3, variable="hp"),
        *[box(10 + i, "wf_xtra_varfx_number", 3, 3, i + 1) for i in range(6)],
        box(2, "wf_trg_says_something", 1, 1, text="go"),
        box(3, "wf_act_give_var", 1, 1, 1, variable="hp"),
    )
    say(engine, "go")
    engine.advance(500)
    assert len(engine.snapshot()["fx"]) == 5
