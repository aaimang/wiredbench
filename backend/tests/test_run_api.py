from __future__ import annotations

from conftest import Api
from wiredbench.engine.tutorials import AVATAR, KEYWORD


def tutorial(api: Api) -> int:
    res = api.post("/api/tutorials/time-tracking", json={})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def run_url(box: int, suffix: str = "") -> str:
    return f"/api/sandboxes/{box}/run{suffix}"


def seconds(state: dict) -> str | None:
    return next((r["value"] for r in state["variables"] if r["variable"] == "seconds"), None)


def test_box_catalogue_lists_settings_and_fidelity(api: Api) -> None:
    boxes = api.get("/api/engine/boxes").json()
    assert boxes["wf_act_send_signal"]["kind"] == "effect"
    assert boxes["wf_act_send_signal"]["fidelity"] == "documented"
    assert {"verified"}.isdisjoint({b["fidelity"] for b in boxes.values()}), "nothing is verified in-game yet"


def test_tutorial_runs_end_to_end_over_the_api(api: Api) -> None:
    box = tutorial(api)
    assert api.get(run_url(box)).status_code == 409, "not started yet"
    assert api.post(run_url(box, "/advance"), json={"ms": 100}).status_code == 409
    started = api.post(run_url(box), json={"seed": 5})
    assert started.status_code == 201
    assert started.json()["seed"] == 5

    api.post(run_url(box, "/input"), json={"type": "move", "user": AVATAR, "x": 4, "y": 4})
    state = api.post(run_url(box, "/advance"), json={"ms": 7000}).json()
    assert seconds(state) is None
    state = api.post(run_url(box, "/input"), json={"type": "say", "user": AVATAR, "text": KEYWORD}).json()
    assert seconds(state) == "7"
    state = api.post(run_url(box, "/advance"), json={"ms": 3000}).json()
    assert seconds(state) == "10"

    api.delete(run_url(box))
    assert api.get(run_url(box)).status_code == 409


def test_trace_is_incremental(api: Api) -> None:
    box = tutorial(api)
    first = api.post(run_url(box), json={"seed": 1}).json()
    cursor = first["trace_next"]
    assert first["trace"]
    state = api.get(run_url(box), params={"since": cursor}).json()
    assert state["trace"] == []
    state = api.post(
        run_url(box, "/input"), params={"since": cursor}, json={"type": "say", "user": AVATAR, "text": "hi"}
    ).json()
    assert [e["message"] for e in state["trace"]] == ["Worker says: hi"]


def test_commands(api: Api) -> None:
    box = tutorial(api)
    api.post(run_url(box), json={"seed": 1})

    def send(text: str) -> str:
        return api.post(run_url(box, "/command"), json={"text": text}).json()["answer"]

    assert send(":vars user worker") == "worker has no variables.", "names match in any case"
    assert send(":set user Worker seconds 40") == "seconds = 40"
    assert "seconds = 40" in send(":vars user Worker")
    assert send(":vars global") == "No global variables are set."
    assert send(":set global x clock 3") == "clock = 3"
    assert "clock = 3" in send(":vars global")
    assert send(":vars furni 1") == "Furni 1 has no variables."
    assert send(":set furni 999 v 1") == "No furni with ID 999."
    assert send(":set user Ghost v 1") == "No user called Ghost."
    assert send(":as Ghost") == "No user called Ghost."
    assert send(":as Worker") == "Acting as Worker."
    assert send(":trace off") == "Trace is off."
    assert send(":trace on") == "Trace is on."

    assert send(":pause") == "Paused."
    now = api.get(run_url(box)).json()["now_ms"]
    assert api.post(run_url(box, "/advance"), json={"ms": 5000}).json()["now_ms"] == now, "paused"
    assert send(":step") == f"Stepped to {(now + 500) / 1000:.1f} s."
    assert send(":resume") == "Running."
    assert api.post(run_url(box, "/advance"), json={"ms": 500}).json()["now_ms"] == now + 1000


def test_commands_outside_the_grammar_do_nothing(api: Api) -> None:
    box = tutorial(api)
    api.post(run_url(box), json={"seed": 1})
    for text in (
        "__import__('os').system('id')",
        ":vars user a b",
        ":set user Worker x 1; drop table folder",
        ":set user Worker x 99999999999999999999",
        ":vars user ../../etc",
        ":VARS global",
        "",
    ):
        res = api.post(run_url(box, "/command"), json={"text": text})
        assert res.status_code == 200
        assert res.json()["answer"].startswith("Commands:")


def test_set_rejects_out_of_range_values(api: Api) -> None:
    box = tutorial(api)
    api.post(run_url(box), json={"seed": 1})
    res = api.post(run_url(box, "/command"), json={"text": f":set user Worker x {2**63}"})
    assert res.json()["answer"] == "That value is out of range."


def test_bad_requests_are_refused(api: Api) -> None:
    box = tutorial(api)
    api.post(run_url(box), json={"seed": 1})
    assert api.post(run_url(box, "/advance"), json={"ms": 10**9}).status_code == 422
    assert api.post(run_url(box, "/advance"), json={"ms": -1}).status_code == 422
    assert api.post(run_url(box, "/input"), json={"type": "explode"}).status_code == 422
    assert api.post(run_url(box, "/input"), json={"type": "say", "text": "x" * 501}).status_code == 422
    assert api.post(run_url(box, "/command"), json={"text": "x" * 201}).status_code == 422
    assert api.post(run_url(999), json={}).status_code == 404


def test_running_too_many_rooms_drops_the_oldest(api: Api) -> None:
    rooms = [tutorial(api) for _ in range(9)]
    for box in rooms:
        assert api.post(run_url(box), json={"seed": 1}).status_code == 201
    assert api.get(run_url(rooms[0])).status_code == 409
    assert api.get(run_url(rooms[-1])).status_code == 200


def test_tutorial_can_be_added_twice_and_saves_valid_room(api: Api) -> None:
    first, second = tutorial(api), tutorial(api)
    names = {s["name"] for s in api.get("/api/workspace/tree").json()["sandboxes"]}
    assert names == {"Time tracking example", "Time tracking example (copy)"}
    document = api.get(f"/api/sandboxes/{first}").json()["document"]
    res = api.put(f"/api/sandboxes/{second}/document", json={"document": document, "base_revision": 2})
    assert res.status_code == 200, res.text


def test_running_a_room_does_not_change_the_saved_document(api: Api) -> None:
    box = tutorial(api)
    before = api.get(f"/api/sandboxes/{box}").json()["document"]
    api.post(run_url(box), json={"seed": 1})
    api.post(run_url(box, "/input"), json={"type": "move", "user": AVATAR, "x": 4, "y": 4})
    api.post(run_url(box, "/advance"), json={"ms": 30000})
    assert api.get(f"/api/sandboxes/{box}").json()["document"] == before


def test_vars_global_shows_zero_before_a_global_is_set(api: Api) -> None:
    box = tutorial(api)
    document = api.get(f"/api/sandboxes/{box}").json()["document"]
    document["furni"].append(
        {"id": 901, "classname": "wf_var_room", "x": 0, "y": 0, "wired": {"variable": "round"}}
    )
    revision = api.get(f"/api/sandboxes/{box}").json()["revision"]
    assert (
        api.put(
            f"/api/sandboxes/{box}/document", json={"document": document, "base_revision": revision}
        ).status_code
        == 200
    )
    state = api.post(run_url(box), json={"seed": 1}).json()
    assert {"variable": "round", "scope": "global"} not in state["defined_variables"]

    def send(text: str) -> str:
        return api.post(run_url(box, "/command"), json={"text": text}).json()["answer"]

    assert "round = 0" in send(":vars global")
    assert send(":set global x round 3") == "round = 3"
    assert "round = 3" in send(":vars global")
