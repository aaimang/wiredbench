from __future__ import annotations

import io
import struct
import zlib

import defusedxml.ElementTree as ET
import pytest
from PIL import Image

from swf_builder import _binary, _image, _symbols, _tag, furni_swf, wrap
from wiredbench.services.swf import (
    MAX_TRACK_FRAMES,
    SwfError,
    _digit_layers,
    _layer_tracks,
    _track_frames,
    build,
)


def test_builds_manifest_and_atlas() -> None:
    manifest, png = build(furni_swf("box"), "box")
    assert manifest["size"] == 64
    assert manifest["directions"] == [2, 4]
    assert manifest["states"] == [0, 1], "transition animations are not states"
    assert manifest["colors"] == {"1": {"0": "ff1f08"}}
    atlas = Image.open(io.BytesIO(png))
    for sprites in manifest["poses"].values():
        for sprite in sprites:
            assert sprite["x"] + sprite["w"] <= atlas.width
            assert sprite["y"] + sprite["h"] <= atlas.height


def test_uncompressed_files_and_colour_variants_work() -> None:
    manifest, _ = build(furni_swf("box", compressed=False), "box*3")
    assert manifest["directions"] == [2, 4]


def test_offsets_layers_and_states() -> None:
    manifest, png = build(furni_swf("box"), "box")
    shadow, base, top = manifest["poses"]["2:0"]
    assert (shadow["layer"], shadow["alpha"]) == (-1, 48)
    assert (base["dx"], base["dy"], base["flip"]) == (-20, -40, False)
    assert (top["alpha"], top["ink"], top["z"]) == (128, "add", 5)

    mirrored = manifest["poses"]["4:0"]
    flipped = next(s for s in mirrored if s["layer"] == 0)
    assert (flipped["dx"], flipped["flip"]) == (30 - 40, True), "measured from the mirrored edge"
    assert next(s for s in mirrored if s["layer"] == 1)["z"] == -3, "direction overrides the layer"
    assert [s["layer"] for s in mirrored] == [1, 0], "sorted back to front"

    atlas = Image.open(io.BytesIO(png)).convert("RGBA")
    state1 = next(s for s in manifest["poses"]["2:1"] if s["layer"] == 0)
    assert atlas.getpixel((base["x"], base["y"])) == (200, 50, 30, 255)
    assert atlas.getpixel((state1["x"], state1["y"])) == (43, 122, 61, 255)


def test_shared_bitmap_under_several_names_is_stored_once() -> None:
    manifest, _ = build(furni_swf("box"), "box")
    a = next(s for s in manifest["poses"]["2:0"] if s["layer"] == 0)
    b = next(s for s in manifest["poses"]["4:0"] if s["layer"] == 0)
    assert (a["x"], a["y"]) == (b["x"], b["y"])


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"nonsense",
        b"NWS\x0a" + bytes(40),
        b"CWS\x0a\0\0\0\0not zlib",
        wrap(b""),
        wrap(_tag(36, b"\x01")),
        wrap(_tag(36, struct.pack("<HBHH", 1, 5, 50000, 50000) + zlib.compress(b"x"))),
        wrap(_tag(36, struct.pack("<HBHH", 1, 9, 2, 2) + zlib.compress(b"x"))),
        wrap(_tag(36, struct.pack("<HBHH", 1, 5, 20, 20) + zlib.compress(b"x"))),
        wrap(struct.pack("<HI", (87 << 6) | 0x3F, 99999) + b"short"),
        wrap(_binary(1, "<not xml") + _symbols({1: ["box_assets"]})),
        wrap(_tag(21, struct.pack("<H", 1) + b"not a jpeg")),
    ],
)
def test_damaged_files_are_refused_cleanly(data: bytes) -> None:
    with pytest.raises(SwfError):
        build(data, "box")


def test_entity_expansion_xml_is_refused() -> None:
    bomb = '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><assets>&b;</assets>'
    data = wrap(_binary(1, bomb) + _symbols({1: ["box_assets"]}))
    with pytest.raises(SwfError):
        build(data, "box")


def test_decompression_bomb_is_refused() -> None:
    data = b"CWS\x0a\0\0\0\0" + zlib.compress(bytes(40 * 2**20))
    with pytest.raises(SwfError):
        build(data, "box")


def test_too_many_images_is_refused() -> None:
    tags = b"".join(_image(i, 4096, 4096, b"\xff\x00\x00\x00") for i in range(1, 2))
    tags += _image(2, 4096, 4096, b"\xff\x00\x00\x00") * 5
    with pytest.raises(SwfError):
        build(wrap(tags), "box")


def test_hostile_symbol_names_cannot_escape_the_manifest() -> None:
    manifest, _ = build(furni_swf("box"), "box")
    assert "../" not in str(manifest)


def test_still_furni_has_no_tracks_or_digits() -> None:
    manifest, _ = build(furni_swf("box"), "box")
    assert manifest["tracks"] == {}
    assert manifest["digits"] == {}


def layer_xml(body: str, **attributes: str) -> ET.Element:
    extras = " ".join(f'{key}="{value}"' for key, value in attributes.items())
    return ET.fromstring(f'<animationLayer id="1" {extras}>{body}</animationLayer>')


def test_track_frames_follow_each_sequence_in_order() -> None:
    body = (
        '<frameSequence loopCount="2"><frame id="1"/><frame id="2"/></frameSequence>'
        '<frameSequence><frame id="3"/></frameSequence>'
    )
    assert _track_frames(layer_xml(body)) == [1, 2, 1, 2, 3]
    huge = '<frameSequence loopCount="99999">' + '<frame id="1"/>' * 50 + "</frameSequence>"
    assert len(_track_frames(layer_xml(huge))) == MAX_TRACK_FRAMES


def test_layer_tracks_keep_speed_and_looping() -> None:
    animation = ET.fromstring(
        '<animation id="1">'
        '<animationLayer id="0"><frameSequence><frame id="0"/></frameSequence></animationLayer>'
        '<animationLayer id="1" frameRepeat="4" loopCount="0">'
        '<frameSequence><frame id="0"/><frame id="1"/></frameSequence></animationLayer>'
        "</animation>"
    )
    tracks = _layer_tracks(animation, 2, lambda _d, layer, frame: {"layer": layer, "frame": frame})
    assert len(tracks) == 1, "a layer with one frame stands still"
    assert (tracks[0]["layer"], tracks[0]["repeat"], tracks[0]["loop"]) == (1, 4, True)
    assert [f["frame"] for f in tracks[0]["frames"]] == [0, 1]


def test_digit_layers_run_left_to_right_and_need_all_ten() -> None:
    def sprite_for(_direction: int, layer: int, frame: int) -> dict[str, int] | None:
        if layer == 0:
            return {"layer": 0, "dx": 0} if frame == 0 else None
        return {"layer": layer, "dx": -layer} if frame < 10 else None

    found = _digit_layers(2, 3, sprite_for)
    assert [slot["0"]["layer"] for slot in found] == [2, 1], "the higher layer sits further left here"


def test_transitions_are_not_states() -> None:
    assert build(furni_swf("box"), "box")[0]["states"] == [0, 1]
