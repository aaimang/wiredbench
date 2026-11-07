from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from conftest import PNG, Api, FakeHabbo
from swf_builder import figure_library
from wiredbench.services import figures

GEOMETRY = b"""<geometry><camera><x>0</x><y>0</y><z>10</z></camera>
  <avatarset id="full">
    <avatarset id="body" main="1"><bodypart id="torso"/><bodypart id="rightarm"/></avatarset>
    <avatarset id="head"><bodypart id="head"/></avatarset>
  </avatarset>
  <type id="vertical">
    <bodypart id="torso" x="0" y="0" z="0" radius="0.4">
      <item id="bd" radius="0.01"/><item id="ch" radius="0.04"/>
    </bodypart>
    <bodypart id="rightarm" x="1" y="0" z="-0.51" radius="0.5">
      <item id="rh" radius="0.01"/><item id="rs" radius="0.04"/>
    </bodypart>
    <bodypart id="head" x="0" y="0" z="0" radius="0.5">
      <item id="hd" radius="0.01"/><item id="ey" radius="0.03"/><item id="hr" radius="0.05"/>
      <item id="hrb" radius="0.06"/>
    </bodypart>
  </type>
</geometry>"""
PART_SETS = b"""<partSets><partSet>
  <part set-type="rh" flipped-set-type="lh"/><part set-type="lh" flipped-set-type="rh"/>
  <part set-type="hrb" remove-set-type="hr"/>
</partSet></partSets>"""
FIGUREDATA = b"""<figuredata><colors>
  <palette id="1"><color id="7">FF0000</color><color id="8">00FF00</color></palette>
</colors><sets>
  <settype type="hd" paletteid="1"><set id="180">
    <part id="1" type="bd" colorable="1" colorindex="1"/><part id="1" type="hd" colorable="1" colorindex="1"/>
    <part id="1" type="ey" colorable="1" colorindex="1"/><part id="1" type="rh" colorable="1" colorindex="1"/>
  </set></settype>
  <settype type="hr" paletteid="1">
    <set id="100"><part id="5" type="hr" colorable="1" colorindex="1"/></set>
    <set id="200"><part id="5" type="hr" colorable="1" colorindex="1"/><part id="9" type="hrb" colorable="0"/></set>
  </settype>
  <settype type="ha" paletteid="1"><set id="1"><part id="3" type="ha" colorable="0"/>
    <hiddenlayers><layer parttype="hrb"/></hiddenlayers></set></settype>
</sets></figuredata>"""
FIGUREMAP = b"""<map><lib id="lib_a" revision="1">
  <part id="1" type="bd"/><part id="1" type="hd"/><part id="1" type="ey"/><part id="1" type="rh"/>
  <part id="5" type="hr"/><part id="3" type="ha"/>
</lib></map>"""
WHITE = b"\xff\xff\xff\xff"


def library() -> figures.Library:
    blocks = {
        "h_std_bd_1_2_0": (4, 4, WHITE, (-10, 90)),
        "h_std_hd_1_2_0": (2, 2, WHITE, (-20, 80)),
        "h_std_ey_1_2_0": (1, 1, WHITE, (-21, 79)),
        "h_std_rh_1_2_0": (2, 2, WHITE, (-30, 60)),
        "h_std_lh_1_2_0": (2, 2, WHITE, (-40, 60)),
        "h_std_hr_5_2_0": (3, 3, WHITE, (-20, 82)),
        "h_std_hrb_9_2_0": (3, 3, b"\xff\xff\x00\x00", (-20, 82)),
    }
    return figures.parse_library(figure_library("lib_a", blocks), "lib_a")


@pytest.fixture
def parts() -> tuple[figures.Rules, figures.FigureData, dict[tuple[str, str], str]]:
    return (
        figures.parse_rules(GEOMETRY, PART_SETS),
        figures.parse_figuredata(FIGUREDATA),
        figures.parse_figuremap(FIGUREMAP),
    )


def draw(parts: tuple, figure: str, direction: int = 2) -> Image.Image:
    rules, data, mapping = parts
    looks = figures.resolve(figure, data, mapping)
    assert looks is not None
    return figures.compose(rules, looks, {"lib_a": library()}, direction, direction)


def test_parts_land_at_habbos_offsets_with_their_colour(parts: tuple) -> None:
    image = draw(parts, "hd-180-7")
    assert image.size == (64, 110)
    assert image.getpixel((10, 10)) == (255, 0, 0, 255), "the body, tinted, at (-x, 100 - y)"
    assert image.getpixel((21, 21)) == (255, 255, 255, 255), "eyes are never tinted"


def test_a_mirrored_direction_uses_the_other_hand_flipped(parts: tuple) -> None:
    image = draw(parts, "hd-180-7", direction=4)
    # rh at direction 4 is lh's direction 2 art (left 40), mirrored: 64 - 40 - 2 = 22.
    assert image.getpixel((22, 40))[3] == 255
    assert image.getpixel((30, 40))[3] == 0


def test_draw_order_follows_the_client_geometry(parts: tuple) -> None:
    rules = parts[0]
    assert rules.order(2, 2)[-1] == "rightarm", "the near arm is drawn last"
    assert rules.order(6, 6)[0] == "rightarm", "and first when the avatar faces the other way"


def test_hidden_layers_and_removed_parts(parts: tuple) -> None:
    alone = draw(parts, "hd-180-7.hr-200-8")
    assert alone.getpixel((20, 18)) == (255, 0, 0, 255), "the back hair replaces the hair"
    hatted = draw(parts, "hd-180-7.hr-200-8.ha-1")
    assert hatted.getpixel((20, 18)) == (0, 255, 0, 255), "a hat hides the back hair, so the hair stays"


ACTIONS = b"""<actions>
  <action id="Sit" state="sit" precedence="103" main="1" geometrytype="vertical" activepartset="sit"
    assetpartdefinition="sit"/>
  <action id="Wave" state="wave" precedence="205" geometrytype="vertical" activepartset="handRight"
    assetpartdefinition="wav"/>
  <action id="Talk" state="talk" precedence="500" geometrytype="vertical" activepartset="head"
    assetpartdefinition="spk"/>
  <action id="Default" precedence="1000" state="std" main="1" isdefault="1" geometrytype="vertical"
    activepartset="figure" assetpartdefinition="std"/>
</actions>"""
ANIMATION = b"""<animationSet>
  <action id="Wave"><part set-type="rh"><frame number="0"/><frame number="1" repeats="4"/></part></action>
  <action id="Talk"><part set-type="hd"><frame number="0"/></part></action>
</animationSet>"""
ACTIVE = b"""<partSets><partSet><part set-type="rh" flipped-set-type="lh"/></partSet>
  <activePartSet id="figure"><activePart set-type="bd"/><activePart set-type="hd"/><activePart set-type="ey"/>
    <activePart set-type="rh"/><activePart set-type="hr"/></activePartSet>
  <activePartSet id="sit"><activePart set-type="bd"/></activePartSet>
  <activePartSet id="handRight"><activePart set-type="rh"/></activePartSet>
  <activePartSet id="head"><activePart set-type="hd"/><activePart set-type="hr"/></activePartSet>
</partSets>"""


def test_a_pose_picks_each_parts_art_by_action_priority() -> None:
    rules = figures.parse_rules(GEOMETRY, ACTIVE, ANIMATION, ACTIONS)
    shown = figures.pose(rules, "sit,wav", "std", 1)
    assert shown is not None
    assert shown.shows(rules, "bd") == ("sit", 0), "sitting owns the body"
    assert shown.shows(rules, "rh") == ("wav", 1), "waving owns the hand, counting each frame once"
    assert shown.shows(rules, "hd") == ("std", 0)
    talking = figures.pose(rules, "std", "spk", 0)
    assert talking is not None
    assert talking.shows(rules, "hd") == ("spk", 0)
    assert talking.shows(rules, "hr") == ("std", 0), "talking changes only the parts its animation lists"
    assert figures.pose(rules, "dance", "std", 0) is None, "the image service draws what this does not know"
    assert figures.pose(rules, "std", "zzz", 0) is None


def test_a_part_without_action_art_is_drawn_standing(parts: tuple) -> None:
    rules = figures.parse_rules(GEOMETRY, ACTIVE, ANIMATION, ACTIONS)
    _, data, mapping = parts
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    sitting = figures.compose(rules, looks, {"lib_a": library()}, 2, 2, figures.pose(rules, "sit", "std", 0))
    assert sitting.getpixel((10, 10)) == (255, 0, 0, 255), "no sitting art for the body, so it stands"


def test_own_direction_art_is_used_instead_of_a_mirror(parts: tuple) -> None:
    rules, data, mapping = parts
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    lib = library()
    lib.images["h_std_rh_1_4_0"] = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    lib.offsets["h_std_rh_1_4_0"] = (-50, 60)
    image = figures.compose(rules, looks, {"lib_a": lib}, 4, 4)
    assert image.getpixel((50, 40)) == (255, 0, 0, 255), "drawn where its own offset says, unmirrored"


def test_unknown_sets_are_not_drawn(parts: tuple) -> None:
    rules, data, mapping = parts
    assert figures.resolve("hd-999-7", data, mapping) is None
    assert figures.resolve("zz-1", data, mapping) is None


def test_the_route_falls_back_to_habbo_when_it_cannot_draw(
    api: Api, habbo: FakeHabbo, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawn = Image.new("RGBA", (64, 110), (1, 2, 3, 255))
    calls: list[str] = []

    def fake(
        self: figures.Figures, hotel: str, figure: str, direction: int, head: int, *pose: object
    ) -> bytes | None:
        calls.append(figure)
        if figure == "hd-9-1":
            return None
        import io

        out = io.BytesIO()
        drawn.save(out, "PNG")
        return out.getvalue()

    monkeypatch.setattr(figures.Figures, "draw", fake)
    ours = api.get("/api/avatars/com/image", params={"figure": "hd-180-1", "drawn_by": "wiredbench"})
    assert ours.status_code == 200 and ours.content != PNG
    fallback = api.get("/api/avatars/com/image", params={"figure": "hd-9-1", "drawn_by": "wiredbench"})
    assert fallback.content == PNG
    waving = api.get(
        "/api/avatars/com/image", params={"figure": "hd-180-1", "drawn_by": "wiredbench", "action": "wav"}
    )
    assert waving.content == ours.content, "poses are drawn here too"
    plain = api.get("/api/avatars/com/image", params={"figure": "hd-180-1"})
    assert plain.content == PNG, "Habbo's image service stays the default"
    assert calls == ["hd-180-1", "hd-9-1", "hd-180-1"]
    assert (
        api.get("/api/avatars/com/image", params={"figure": "hd-180-1", "drawn_by": "evil"}).status_code
        == 422
    )


def test_the_setting_is_saved(api: Api, tmp_path: Path) -> None:
    assert api.get("/api/settings").json()["avatar_drawing"] == "habbo"
    assert (
        api.patch("/api/settings", json={"avatar_drawing": "wiredbench"}).json()["avatar_drawing"]
        == "wiredbench"
    )
    assert api.patch("/api/settings", json={"avatar_drawing": "evil"}).status_code == 422


BOARD = """<animation name="fx.2">
  <sprite id="avatar"/>
  <add id="fx1_1" align="torso"/>
  <remove id="hd"/>
  <frame>
    <fx id="avatar" frame="0" dy="-20"/>
    <fx id="fx1_1" frame="0"/>
    <bodypart id="torso" action="Default" frame="0"/>
    <bodypart id="head"><item id="ey" base="fx1_1"/></bodypart>
  </frame>
  <frame repeats="2"><fx id="avatar" frame="0" dy="-10"/><fx id="fx1_1" frame="1"/></frame>
</animation>"""


def test_an_effect_lifts_the_avatar_adds_and_swaps_parts_and_removes_others(parts: tuple) -> None:
    from swf_builder import effect_swf

    rules, data, mapping = parts
    parsed = figures.parse_effect(effect_swf("Board", BOARD), "Board")
    assert parsed is not None
    art, animation = parsed
    assert len(animation.frames) == 3, "a repeated frame counts twice for playing"
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    image = figures.compose_effect(
        rules,
        looks,
        {"lib_a": library(), "Board": art},
        2,
        2,
        figures.Pose("vertical", [], [], 0),
        animation,
        0,
    )
    margin_x, margin_top, margin_bottom = figures.EFFECT_MARGIN
    assert image.size == (64 + 2 * margin_x, 110 + margin_top + margin_bottom)
    body = image.getpixel((margin_x + 10, margin_top + 10 - 20))
    assert body == (255, 0, 0, 255), "the body is drawn 20 pixels higher"
    assert image.getpixel((margin_x + 20, margin_top + 20 - 20))[3] == 0, "the head is removed"
    added = image.getpixel((margin_x + 10, margin_top + 100 - 80 - 20))
    assert added[3] == 255, "the effect's own part is drawn on the torso"


def test_recolouring_shades_between_two_colours() -> None:
    white = Image.new("RGBA", (2, 1), (255, 255, 255, 255))
    white.putpixel((1, 0), (0, 0, 0, 255))
    shaded = figures.recolour(white, 4, "#00FFFF", "#FFFFFF")
    assert shaded.getpixel((0, 0)) == (0, 255, 255, 255), "light art takes the foreground"
    assert shaded.getpixel((1, 0)) == (255, 255, 255, 255), "dark art takes the background"
    assert figures.recolour(white, 37, "FFFFFFFF", "66000000").getpixel((0, 0))[3] == 127, (
        "ink 37 halves opacity"
    )


def test_effects_are_only_drawn_by_wiredbench(
    api: Api, habbo: FakeHabbo, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    out = io.BytesIO()
    Image.new("RGBA", (96, 210), (1, 2, 3, 255)).save(out, "PNG")
    calls: list[object] = []

    def fake(self: figures.Figures, *args: object) -> bytes:
        calls.append(args[8])  # The effect's own frame.
        return out.getvalue()

    monkeypatch.setattr(figures.Figures, "draw", fake)
    params = {"figure": "hd-180-1", "effect": 2, "effect_frame": 12}
    assert api.get("/api/avatars/com/image", params=params).status_code == 404, "Habbo draws no effects"
    drawn = api.get("/api/avatars/com/image", params={**params, "drawn_by": "wiredbench"})
    assert drawn.status_code == 200 and calls == [12]
    assert api.get("/api/avatars/com/image", params={"figure": "hd-180-1", "frame": 12}).status_code == 422
    no_effect = {"figure": "hd-180-1", "effect_frame": 3, "drawn_by": "wiredbench"}
    assert api.get("/api/avatars/com/image", params=no_effect).status_code == 422


def test_walking_with_an_effect_keeps_the_steps_apart_from_the_effects_frame(
    api: Api, habbo: FakeHabbo, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    out = io.BytesIO()
    Image.new("RGBA", (96, 210), (1, 2, 3, 255)).save(out, "PNG")
    calls: list[tuple[object, ...]] = []

    def fake(self: figures.Figures, *args: object) -> bytes:
        calls.append(args)
        return out.getvalue()

    monkeypatch.setattr(figures.Figures, "draw", fake)
    base = {"figure": "hd-180-1", "action": "wlk", "effect": 27, "drawn_by": "wiredbench"}
    for step in range(4):
        assert api.get("/api/avatars/com/image", params={**base, "frame": step}).status_code == 200
    # Before, one frame value served both, so an effect with one frame held the legs still.
    # Gesture, the walk's step, the effect, and the effect's own frame.
    assert [call[5:9] for call in calls] == [("std", step, 27, 0) for step in range(4)]
    api.get("/api/avatars/com/image", params={**base, "frame": 1, "direction": 6, "effect_frame": 5})
    assert calls[-1][2:4] == (6, 6) and calls[-1][6:9] == (1, 27, 5), "a turn and a later effect frame"


OVERRIDDEN = """<animation name="fx.38">
  <sprite id="avatar"/>
  <shadow id="std_fx1_sd_0"/>
  <frame><fx id="avatar" frame="0" dy="-20"/></frame>
  <override name="skate" override="mv">
    <frame><fx id="avatar" frame="0" dy="-10"/></frame>
    <frame repeats="2"><fx id="avatar" frame="0" dy="-5"/></frame>
  </override>
</animation>"""


def move(state: str) -> figures.Action:
    return figures.Action(state, "wlk" if state == "mv" else "std", 600, "vertical", "walk", False, state)


def test_an_override_plays_instead_while_the_avatar_does_its_action(parts: tuple) -> None:
    from swf_builder import effect_swf

    rules, data, mapping = parts
    parsed = figures.parse_effect(effect_swf("Skate", OVERRIDDEN, shadow="std_fx1_sd_0"), "Skate")
    assert parsed is not None
    art, animation = parsed
    assert len(animation.frames) == 1, "an override's frames are not played after the effect's own"
    assert len(animation.overrides["mv"]) == 3
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    margin_x, margin_top, _ = figures.EFFECT_MARGIN

    def lifted(*actions: figures.Action, frame: int = 0) -> int:
        shown = figures.Pose("vertical", list(actions), [], 0)
        image = figures.compose_effect(
            rules, looks, {"lib_a": library(), "Skate": art}, 2, 2, shown, animation, frame
        )
        column = [image.getpixel((margin_x + 10, y)) for y in range(image.height)]
        return margin_top + 10 - next(y for y, pixel in enumerate(column) if pixel == (255, 0, 0, 255))

    assert lifted(move("std")) == 20, "standing plays the effect's own frames"
    assert lifted(move("mv"), move("std")) == 10, "walking plays the override"
    assert lifted(move("mv"), move("std"), frame=2) == 5, "the override's frames repeat as listed"


def test_an_effects_shadow_stays_on_the_floor(parts: tuple) -> None:
    from swf_builder import effect_swf

    rules, data, mapping = parts
    parsed = figures.parse_effect(effect_swf("Skate", OVERRIDDEN, shadow="std_fx1_sd_0"), "Skate")
    assert parsed is not None
    art, animation = parsed
    assert animation.shadow == "std_fx1_sd_0"
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    image = figures.compose_effect(
        rules,
        looks,
        {"lib_a": library(), "Skate": art},
        2,
        2,
        figures.Pose("vertical", [], [], 0),
        animation,
        0,
    )
    margin_x, margin_top, _ = figures.EFFECT_MARGIN
    # Art without an offset sits at the origin, which a lift of 20 does not move.
    assert image.getpixel((margin_x + 1, margin_top + 101)) == (0, 0, 0, figures.SHADOW_ALPHA)
    plain = figures.parse_effect(effect_swf("Skate", OVERRIDDEN), "Skate")
    assert plain is not None
    without = figures.compose_effect(
        rules,
        looks,
        {"lib_a": library(), "Skate": plain[0]},
        2,
        2,
        figures.Pose("vertical", [], [], 0),
        plain[1],
        0,
    )
    assert without.getpixel((margin_x + 1, margin_top + 101))[3] == 0, "no shadow art, no shadow"


def test_effect_actions_are_found_by_id_or_state() -> None:
    rules = figures.parse_rules(GEOMETRY, PART_SETS, actions=ACTIONS)
    assert rules.posed("Sit", "bd", 0) == ("sit", 0)
    assert rules.posed("std", "bd", 0) == ("std", 0), "some effects name the default action by its state"


def held_or_worn(removes: str) -> str:
    return f"""<animation name="fx.247">{removes}
  <sprite id="fx1_1" member="std_fx1_1_1"><direction id="0" dz="0"/></sprite>
  <frame><fx id="fx1_1" frame="0" dx="10"/></frame>
</animation>"""


def test_the_head_goes_over_a_body_the_effect_draws_itself(parts: tuple) -> None:
    from swf_builder import effect_swf

    rules, data, mapping = parts
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    margin_x, margin_top, _ = figures.EFFECT_MARGIN

    def at_head(removes: str) -> tuple[int, ...]:
        art, animation = figures.parse_effect(effect_swf("Fx", held_or_worn(removes)), "Fx") or (None, None)
        assert art and animation
        image = figures.compose_effect(
            rules,
            looks,
            {"lib_a": library(), "Fx": art},
            2,
            2,
            figures.Pose("vertical", [], [], 0),
            animation,
            0,
        )
        return image.getpixel((margin_x + 20, margin_top + 20))

    assert at_head("") == (255, 255, 0, 255), "a held item at depth 0 is in front, as a staff in the hand"
    assert at_head('<remove id="bd"/>') == (255, 0, 0, 255), "a broom rider's cloak goes under the head"


def test_art_off_the_canvas_draws_nothing_and_never_fails() -> None:
    canvas = Image.new("RGBA", (10, 10))
    dot = Image.new("RGBA", (1, 1), (255, 0, 0, 255))
    for left, top in ((-8, 0), (0, -8), (12, 0), (0, 12)):
        figures.paste(canvas, dot, left, top)
    assert canvas.getbbox() is None
    figures.paste(canvas, Image.new("RGBA", (4, 4), (255, 0, 0, 255)), -2, 8)
    assert canvas.getbbox() == (0, 8, 2, 10), "only the part on the canvas"


WALK_PARTS = b"""<partSets><partSet/>
  <activePartSet id="walk"><activePart set-type="bd"/><activePart set-type="rh"/></activePartSet>
  <activePartSet id="handRightAndHead"><activePart set-type="rh"/></activePartSet>
  <activePartSet id="figure"><activePart set-type="bd"/><activePart set-type="rh"/></activePartSet>
</partSets>"""
WALK_ACTIONS = b"""<actions>
  <action id="Blow" state="blow" precedence="211" geometrytype="vertical" activepartset="handRightAndHead"
    assetpartdefinition="blw"/>
  <action id="Move" state="mv" precedence="600" geometrytype="vertical" activepartset="walk"
    assetpartdefinition="wlk"/>
  <action id="Default" precedence="1000" state="std" main="1" isdefault="1" geometrytype="vertical"
    activepartset="figure" assetpartdefinition="std"/>
</actions>"""
WALK_ANIMATION = b"""<animationSet>
  <action id="Move">
    <part set-type="bd"><frame number="0"/><frame number="1"/><frame number="2"/><frame number="3"/></part>
    <part set-type="rh"><frame number="0"/><frame number="1"/><frame number="2"/><frame number="3"/></part>
  </action>
  <action id="Blow">
    <part set-type="rh"><frame number="0" repeats="10"/><frame number="1" repeats="10"/></part>
  </action>
</animationSet>"""


def test_a_kiss_while_walking_keeps_its_own_frame() -> None:
    rules = figures.parse_rules(GEOMETRY, WALK_PARTS, WALK_ANIMATION, WALK_ACTIONS)
    stepping = figures.pose(rules, "wlk,blw", "std", 3)
    assert stepping is not None
    assert stepping.shows(rules, "rh") == ("blw", 1), "without its own frame, the kiss follows the step"
    kissing = figures.pose(rules, "wlk,blw", "std", 3, action_frame=0)
    assert kissing is not None
    assert kissing.shows(rules, "rh") == ("blw", 0), "the kiss keeps its own frame"
    assert kissing.shows(rules, "bd") == ("wlk", 3), "and the legs keep stepping"


def test_an_effect_raises_the_avatar_in_each_direction(parts: tuple) -> None:
    from swf_builder import effect_swf

    rules, data, mapping = parts
    skates = """<animation name="fx.55">
      <sprite id="avatar"><direction id="2" dy="-8"/><direction id="4" dy="-8"/></sprite>
      <frame><fx id="avatar" frame="0"/></frame>
    </animation>"""
    parsed = figures.parse_effect(effect_swf("Skates", skates), "Skates")
    assert parsed is not None
    art, animation = parsed
    assert animation.avatar_shift[2] == (0, -8)
    looks = figures.resolve("hd-180-7", data, mapping)
    assert looks is not None
    image = figures.compose_effect(
        rules,
        looks,
        {"lib_a": library(), "Skates": art},
        2,
        2,
        figures.Pose("vertical", [], [], 0),
        animation,
        0,
    )
    margin_x, margin_top, _ = figures.EFFECT_MARGIN
    assert image.getpixel((margin_x + 10, margin_top + 10 - 8)) == (255, 0, 0, 255), "the body is 8 higher"


def test_an_actions_own_frame_reaches_the_drawing(
    api: Api, habbo: FakeHabbo, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    out = io.BytesIO()
    Image.new("RGBA", (64, 110), (1, 2, 3, 255)).save(out, "PNG")
    calls: list[tuple[object, ...]] = []

    def fake(self: figures.Figures, *args: object) -> bytes:
        calls.append(args)
        return out.getvalue()

    monkeypatch.setattr(figures.Figures, "draw", fake)
    params = {
        "figure": "hd-180-1",
        "action": "wlk,blw",
        "frame": 2,
        "action_frame": 1,
        "drawn_by": "wiredbench",
    }
    assert api.get("/api/avatars/com/image", params=params).status_code == 200
    assert calls[-1][6] == 2 and calls[-1][-1] == 1, "the step and the kiss's own frame"
    assert api.get("/api/avatars/com/image", params={**params, "action_frame": 4}).status_code == 422
