from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from PIL import Image

from conftest import FakeHabbo
from wiredbench.services import handitems
from wiredbench.services.assets import AssetCache
from wiredbench.services.upstream import Upstream

FIGURE = "hd-180-1.ch-210-66.lg-270-82"
ACTIONS = b"""<?xml version="1.0"?><actions>
  <action id="UseItem" state="usei"><param id="default" value="9"/><param id="1" value="8"/></action>
  <action id="CarryItem" state="cri">
    <param id="default" value="1"/>
    <param id="1" value="6"/>
    <param id="1000" value="76"/>
    <param id="1128" value="311"/>
    <param id="999999999" value="-1"/>
  </action>
</actions>"""
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


def png(color: tuple[int, int, int, int] = (0, 0, 0, 0), body: bool = False) -> bytes:
    image = Image.new("RGBA", (64, 110), color)
    if body:
        image.paste(BLUE, (20, 20, 40, 100))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def art(monkeypatch: pytest.MonkeyPatch) -> None:
    """Art 311 is a 2x2 red square, offset so that it lands at (25, 40)."""
    square = Image.new("RGBA", (2, 2), RED)
    images = {f"h_crr_ri_311_{direction}_0": square for direction in range(8)}
    offsets = dict.fromkeys(images, (-25, 60))
    monkeypatch.setattr(handitems, "_parse_art", lambda body: (images, offsets))


@pytest.fixture
def cache(tmp_path: Path, habbo: FakeHabbo) -> AssetCache:
    habbo.set(b"other=1\nflash.client.url=//images.habbo.com/gordon/BUILD-1/\n", 'W/"v"')
    habbo.files |= {"HabboAvatarActions.xml": ACTIONS, "hh_human_item.swf": b"swf"}
    habbo.avatar = png(body=True)
    return AssetCache(tmp_path / "furni", Upstream(httpx.MockTransport(habbo)))


def sent_actions(habbo: FakeHabbo) -> list[str]:
    return [r.url.params["action"] for r in habbo.requests if r.url.path.endswith("/avatarimage")]


@pytest.mark.parametrize(
    ("value", "asked"),
    [
        ("crr=1", "crr=6"),
        ("wlk,crr=1000", "wlk,crr=76"),
        ("sit,sig=6,crr=1000", "sit,sig=6,crr=76"),
        ("crr=5000", "crr=1"),  # Not in the map, so the map's default.
        ("wlk,crr=999999999", "wlk"),
        ("crr=999999999", "std"),
    ],
)
def test_a_hand_item_is_asked_for_by_its_art(
    cache: AssetCache, habbo: FakeHabbo, art: None, value: str, asked: str
) -> None:
    habbo.avatar = png(RED)
    assert cache.avatar("com", FIGURE, value, "std", 2, 0) is not None
    assert sent_actions(habbo)[0] == asked


def test_other_actions_never_load_the_hand_item_files(cache: AssetCache, habbo: FakeHabbo) -> None:
    assert cache.avatar("com", FIGURE, "wlk", "std", 2, 0) is not None
    assert not [r for r in habbo.requests if not r.url.path.endswith("/avatarimage")]


def test_art_the_image_service_lacks_is_drawn(cache: AssetCache, habbo: FakeHabbo, art: None) -> None:
    path = cache.avatar("com", FIGURE, "wlk,crr=1128", "std", 2, 1)
    assert path is not None
    image = Image.open(path).convert("RGBA")
    assert image.getpixel((25, 40)) == RED, "on top of the body, at Habbo's offset"
    assert image.getpixel((26, 41)) == RED
    assert image.getpixel((21, 40)) == BLUE
    assert "wlk,crr=311" in sent_actions(habbo)


def test_a_drawn_item_goes_behind_the_body_in_back_directions(
    cache: AssetCache, habbo: FakeHabbo, art: None
) -> None:
    path = cache.avatar("com", FIGURE, "crr=1128", "std", 7, 0)
    assert path is not None
    assert Image.open(path).convert("RGBA").getpixel((25, 40)) == BLUE


def test_art_the_image_service_has_is_left_alone(cache: AssetCache, habbo: FakeHabbo, art: None) -> None:
    real = habbo.__call__

    def answer(request: httpx.Request) -> httpx.Response:
        response = real(request)
        if request.url.params.get("action") == "crr=311":
            return httpx.Response(200, content=png(RED))
        return response

    cache.upstream = Upstream(httpx.MockTransport(answer))
    cache.hand_items.upstream = cache.upstream
    path = cache.avatar("com", FIGURE, "crr=1128", "std", 2, 0)
    assert path is not None
    assert path.read_bytes() == png(RED)


def test_the_item_is_still_held_if_the_map_is_unreachable(cache: AssetCache, habbo: FakeHabbo) -> None:
    habbo.files.pop("HabboAvatarActions.xml")
    assert cache.avatar("com", FIGURE, "crr=5", "std", 2, 0) is not None
    assert sent_actions(habbo) == ["crr=5"]
    before = len(habbo.requests)
    assert cache.avatar("com", FIGURE, "crr=7", "std", 2, 0) is not None
    assert [r for r in habbo.requests[before:] if not r.url.path.endswith("/avatarimage")] == []


def test_the_map_is_read_from_the_client_folder_once(cache: AssetCache, habbo: FakeHabbo, art: None) -> None:
    habbo.avatar = png(RED)
    for value in ("crr=1", "crr=1000", "wlk,crr=1"):
        assert cache.avatar("com", FIGURE, value, "std", 2, 0) is not None
    asked = [r.url.path for r in habbo.requests if r.url.host == "images.habbo.com"]
    assert asked == ["/gordon/BUILD-1/HabboAvatarActions.xml", "/gordon/BUILD-1/hh_human_item.swf"]
