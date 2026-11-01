"""The guide and the example rooms."""

from __future__ import annotations

from conftest import Api, FakeHabbo, apply_update, furni, furnidata
from wiredbench.engine.boxes import BOXES
from wiredbench.engine.core import Engine
from wiredbench.engine.guide import GUIDE
from wiredbench.engine.tutorials import AVATAR, TUTORIALS, score_counter, signal_relay, switch_flip
from wiredbench.services import exchange, room


def test_every_simulated_box_is_explained() -> None:
    assert set(GUIDE) == set(BOXES)
    assert all(purpose and example for purpose, example in GUIDE.values())


def test_guide_without_a_catalogue_still_lists_simulated_boxes(api: Api) -> None:
    rows = api.get("/api/guide").json()["rows"]
    assert {row["classname"] for row in rows} == set(BOXES)
    by_name = {row["classname"]: row for row in rows}
    assert by_name["wf_act_toggle_state"]["status"] == "real_room"
    assert by_name["wf_trg_room_initializes"]["status"] == "assumed"
    assert by_name["wf_trg_at_given_time"]["status"] == "documented"


def test_guide_adds_catalogue_names_and_unsimulated_boxes(api: Api, habbo: FakeHabbo) -> None:
    habbo.set(
        furnidata(
            furni("wf_act_toggle_state", name="Toggle Furni State"),
            furni("wf_act_brand_new", description="From the catalogue", offerid=-1, bc=False),
            furni("chair"),
        ),
        'W/"guide"',
    )
    apply_update(api)
    rows = {
        row["classname"]: row for row in api.get("/api/guide", params={"hotel": "sandbox"}).json()["rows"]
    }
    assert rows["wf_act_toggle_state"]["name"] == "Toggle Furni State"
    assert rows["wf_act_brand_new"]["status"] == "not_simulated"
    assert rows["wf_act_brand_new"]["purpose"] == "From the catalogue"
    assert rows["wf_act_brand_new"]["release_stage"] == "not_in_catalogue"
    assert "chair" not in rows, "only WIRED belongs here"


def test_tutorials_are_listed_and_can_be_added(api: Api) -> None:
    listed = api.get("/api/tutorials").json()
    assert {row["slug"] for row in listed} == set(TUTORIALS)
    assert all("build" not in row for row in listed)
    assert api.post("/api/tutorials/nope", json={}).status_code == 404
    for slug, item in TUTORIALS.items():
        res = api.post(f"/api/tutorials/{slug}", json={})
        assert res.status_code == 201, slug
        assert res.json()["name"] == item["title"]
        room.validate(item["build"]("sandbox"))


def test_switch_rooms_export_with_known_values() -> None:
    document = TUTORIALS["switch-flip"]["build"]("sandbox")
    document["avatars"] = []
    assert exchange.export_gpresets(document)[1] == []
    relay = TUTORIALS["signal-relay"]["build"]("sandbox")
    relay["avatars"] = []
    assert [w for w in exchange.export_gpresets(relay)[1] if "user_source" not in w] == []


def state_of(engine: Engine, furni_id: int) -> int:
    return engine.furni[furni_id]["state"]


def test_switch_flip_works() -> None:
    engine = Engine(switch_flip())
    engine.apply_input({"type": "use", "user": AVATAR, "furni": 1})
    assert state_of(engine, 2) == 1
    engine.apply_input({"type": "use", "user": AVATAR, "furni": 1})
    assert state_of(engine, 2) == 0


def test_signal_relay_works() -> None:
    engine = Engine(signal_relay())
    engine.apply_input({"type": "use", "user": AVATAR, "furni": 1})
    assert state_of(engine, 2) == 1
    assert engine.metrics["signals"] == 1


def test_score_counter_works() -> None:
    engine = Engine(score_counter())
    for expected in ("1", "2", "3"):
        engine.apply_input({"type": "say", "user": AVATAR, "text": "point"})
        rows = [r for r in engine.view_variables() if r["variable"] == "score"]
        assert rows[0]["value"] == expected
