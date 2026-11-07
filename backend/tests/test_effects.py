from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from conftest import Api, FakeHabbo
from swf_builder import effect_swf
from wiredbench.services import effects
from wiredbench.services.upstream import Upstream

EFFECT_MAP = b"""<?xml version="1.0"?><map>
  <effect id="dance.1" lib="Dance1" type="dance"/>
  <effect id="1" lib="Glow" type="fx"/>
  <effect id="2" lib="Board" type="fx"/>
  <effect id="3" lib="../evil" type="fx"/>
</map>"""
OVERLAY = """<animation name="fx.1">
  <sprite id="fx1_1" ink="33" member="std_fx1_1_1" directions="1">
    <direction id="0" dz="1"/><direction id="2" dz="-1" dx="3"/>
  </sprite>
  <frame><fx id="fx1_1" action="Default" frame="0"/></frame>
  <frame repeats="2"><fx id="fx1_1" action="Default" frame="1" dy="-4"/></frame>
</animation>"""
BODY = """<animation name="fx.2">
  <add id="board" align="bottom" base="1"/>
  <sprite id="avatar" member="std_x"/>
  <frame><bodypart id="torso" action="Default" frame="0"/></frame>
</animation>"""


def test_effect_map_keeps_only_safe_effect_files() -> None:
    assert effects.parse_map(EFFECT_MAP) == {1: "Glow", 2: "Board"}


def test_an_overlay_effect_is_built_into_a_sprite_sheet() -> None:
    manifest, sheet = effects.build(effect_swf("Glow", OVERLAY), "Glow")
    assert manifest["drawable"] and sheet is not None
    assert len(manifest["frames"]) == 3, "a repeated frame counts twice"
    assert manifest["frames"][1] == [{"s": "fx1_1", "f": 1, "dy": -4}]
    [sprite] = manifest["sprites"]
    assert sprite["add"] and sprite["turns"]
    assert sprite["dirs"]["2"] == {"dx": 3, "dy": 0, "dz": -1}
    images = manifest["images"]
    assert images["std_fx1_1_1_0_1"]["ox"] == -12
    assert "std_fx1_1_1_2_0" in images, "a plain alias is resolved"
    assert "std_fx1_1_1_4_0" not in images, "a mirrored alias is skipped"


def test_an_effect_that_changes_the_body_is_not_drawn() -> None:
    manifest, sheet = effects.build(effect_swf("Board", BODY), "Board")
    assert sheet is None
    assert manifest == {
        "drawable": False,
        "why": ["add", "avatar", "bodypart"],
        "frame_count": 1,
        "lift": 0,
    }


@pytest.fixture
def fx(habbo: FakeHabbo) -> FakeHabbo:
    habbo.set(b"flash.client.url=//images.habbo.com/gordon/BUILD-1/\n", 'W/"v"')
    habbo.files |= {
        "effectmap.xml": EFFECT_MAP,
        "Glow.swf": effect_swf("Glow", OVERLAY),
        "Board.swf": effect_swf("Board", BODY),
    }
    return habbo


def test_effect_routes_build_once(api: Api, fx: FakeHabbo) -> None:
    manifest = api.get("/api/effects/com/1/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["lib"] == "Glow"
    atlas = api.get("/api/effects/com/1/atlas")
    assert atlas.status_code == 200 and atlas.content.startswith(b"\x89PNG")
    fetched = len(fx.requests)
    api.get("/api/effects/com/1/manifest")
    assert len(fx.requests) == fetched, "built once, then read from disk"


def test_effect_routes_for_body_and_unknown_effects(api: Api, fx: FakeHabbo) -> None:
    assert api.get("/api/effects/com/2/manifest").json()["drawable"] is False
    assert api.get("/api/effects/com/2/atlas").status_code == 404
    assert api.get("/api/effects/com/9/manifest").status_code == 404
    assert api.get("/api/effects/com/0/manifest").status_code == 422
    assert api.get("/api/effects/evil/1/manifest").status_code == 422


def test_unreachable_habbo_is_a_clear_error(tmp_path: Path, fx: FakeHabbo) -> None:
    fx.fail = True
    service = effects.Effects(tmp_path, Upstream(httpx.MockTransport(fx)))
    with pytest.raises(effects.UpstreamError):
        service.files("com", 1)
    assert not json.dumps([str(p) for p in tmp_path.rglob("*")]).count(".json")


def test_the_list_of_drawable_effects_is_served(api: Api) -> None:
    found = api.get("/api/engine/effects").json()
    assert set(found["drawn"]) <= set(found["checked"])
    assert 4 in found["drawn"], "Twinkle only adds sparkles"
    assert 2 not in found["drawn"], "a hoverboard changes the body"


DUCK = """<animation name="fx.170">
  <remove id="hd"/>
  <override name="mv_duck" override="mv">
    <frame><bodypart id="head"/></frame>
    <frame repeats="3"><bodypart id="head"/></frame>
  </override>
</animation>"""


def test_frames_played_only_while_walking_are_counted() -> None:
    manifest, _ = effects.build(effect_swf("Duck", DUCK), "Duck")
    assert manifest["frame_count"] == 4, "a duck has frames only for walking"


def test_an_effect_file_is_downloaded_once_for_layers_and_drawing(api: Api, fx: FakeHabbo) -> None:
    services = api.services
    assert services.assets.figures.effects is services.assets.effects
    assert api.get("/api/effects/com/2/manifest").status_code == 200
    base, build = services.assets.effects._client("com")
    services.assets.figures.effects.library(base, build, "Board")
    board = [request for request in fx.requests if request.url.path.endswith("/Board.swf")]
    assert len(board) == 1
    with pytest.raises(ValueError):
        services.assets.effects.library(base, build, "../evil")


def test_a_body_effect_says_how_high_it_lifts_the_avatar() -> None:
    lifting = """<animation name="fx.247"><sprite id="avatar"/><remove id="bd"/>
      <frame><fx id="avatar" frame="0" dy="-23"/></frame>
      <frame><fx id="avatar" frame="0" dy="-25"/></frame>
    </animation>"""
    manifest, _ = effects.build(effect_swf("Broom", lifting), "Broom")
    assert manifest["lift"] == 25, "the highest the avatar goes, so labels stay clear of the head"


def test_skates_count_their_raise_in_every_direction() -> None:
    skates = """<animation name="fx.55"><sprite id="avatar"><direction id="2" dy="-8"/></sprite>
      <remove id="sh"/><frame><fx id="avatar" frame="0" dy="-2"/></frame>
    </animation>"""
    manifest, _ = effects.build(effect_swf("Skates", skates), "Skates")
    assert manifest["lift"] == 10
