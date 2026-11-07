"""What each @effect looks like, from the effect files Habbo's own client loads.

The avatar image service draws no effects. effectmap.xml names the file for each effect, and an
effect that only adds layers around the avatar can be drawn from that file. Effects that move,
add, remove or recolour body parts need Habbo's own avatar renderer, so they are marked as not
drawn. Nothing is stored in the repo: the files are fetched on first use and built once.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET  # noqa: S405 - Only for the error type. defusedxml does the parsing.
from importlib import resources
from pathlib import Path
from typing import Any

from defusedxml.ElementTree import fromstring as safe_fromstring

from wiredbench.services import swf
from wiredbench.services.handitems import CHECK_SECONDS, RETRY_SECONDS, client_folder
from wiredbench.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)

MAX_MAP_BYTES = 2 * 2**20
MAX_EFFECT_BYTES = 8 * 2**20
LIBRARY = re.compile(r"^[A-Za-z0-9_]{1,64}$")
# Animation parts that change the avatar itself rather than adding layers around it.
BODY_CHANGES = {"add", "remove", "override", "avatar", "direction"}
INK_ADD = "33"
MAX_FRAMES = 2000
# Raised when the manifest's shape changes, so effects built before are built again.
EFFECT_VERSION = 6


def facts() -> dict[str, Any]:
    """Which effects were found drawable when the list was last made with scripts/effect_facts.py."""
    text = resources.files("wiredbench.services").joinpath("effect_facts.json").read_text(encoding="utf-8")
    return dict(json.loads(text))


def parse_map(body: bytes) -> dict[int, str]:
    """Effect ID to file name. Dances are listed too, under other IDs, and are left out."""
    found: dict[int, str] = {}
    for effect in safe_fromstring(body).iter("effect"):
        lib, raw = effect.get("lib", ""), effect.get("id", "")
        if effect.get("type") == "fx" and raw.isdigit() and LIBRARY.fullmatch(lib):
            found[int(raw)] = lib
    return found


def _int(element: ET.Element, name: str) -> int:
    try:
        return int(element.get(name, "0"))
    except ValueError:
        return 0


def build(data: bytes, lib: str) -> tuple[dict[str, Any], bytes | None]:
    """The manifest the room draws from, and its sprite sheet. No sheet when it cannot be drawn."""
    parsed = swf.parse(data)
    animation = manifest = None
    for binary in parsed.binaries.values():
        if b"<animation" in binary[:400]:
            animation = safe_fromstring(binary)
        elif b"<manifest" in binary[:400]:
            manifest = safe_fromstring(binary)
    if animation is None or manifest is None:
        return {"drawable": False, "why": ["no animation"]}, None
    if animation.tag != "animation":
        animation = next(animation.iter("animation"), animation)
    why = {child.tag for child in animation if child.tag in BODY_CHANGES}
    sprites = [child for child in animation if child.tag == "sprite"]
    if any(sprite.get("id") == "avatar" for sprite in sprites):
        why.add("avatar")
    frames: list[list[dict[str, Any]]] = []
    for frame in (child for child in animation if child.tag == "frame"):
        if any(part.tag != "fx" for part in frame):
            why.add("bodypart")
        shown = [
            {
                "s": part.get("id", ""),
                "f": _int(part, "frame"),
                **{key: _int(part, key) for key in ("dx", "dy", "dd") if part.get(key)},
            }
            for part in frame
            if part.tag == "fx"
        ]
        frames.extend([shown] * max(1, _int(frame, "repeats")))
    if not sprites:
        why.add("no sprites")
    if why:
        # The frame count lets the room play a body-changing effect drawn from its parts. Some effects
        # play only frames that stand in for an action, such as a duck that walks, so those count too.
        played = [len(frames)] + [
            sum(max(1, _int(frame, "repeats")) for frame in override.findall("frame"))
            for override in animation.findall("override")
        ]
        # How high the effect lifts the avatar at most, so the room can keep its labels clear of the head.
        lifts = [
            -_int(part, "dy")
            for frame in animation.iter("frame")
            for part in frame.findall("fx")
            if part.get("id") == "avatar"
        ]
        # Skates and boards also raise the avatar in each direction.
        raised = [
            -_int(direction, "dy")
            for sprite in sprites
            if sprite.get("id") == "avatar"
            for direction in sprite.findall("direction")
        ]
        if raised:
            lifts = [lift + max(0, *raised) for lift in lifts] or [max(0, *raised)]
        # Whether the room's own floor shadow stays: the effect may remove it or draw its own instead.
        removed = {child.get("id") for child in animation if child.tag == "remove"}
        own = animation.find("shadow")
        own_art = own is not None and f"{lib}_h_{own.get('id', '')}_0" in parsed.named_images()
        shadow = "none" if "sd" in removed else "own" if own_art else "plain"
        return {
            "drawable": False,
            "why": sorted(why),
            "frame_count": max(1, *played),
            "lift": max(0, *lifts) if lifts else 0,
            "shadow": shadow,
        }, None
    if len(frames) > MAX_FRAMES:
        return {"drawable": False, "why": ["too many frames"]}, None

    images = {
        name[len(lib) + 1 :]: image.convert("RGBA")
        for name, image in parsed.named_images().items()
        if name.startswith(f"{lib}_h_")
    }
    offsets: dict[str, tuple[int, int]] = {}
    for asset in manifest.iter("asset"):
        param = asset.find("param")
        x, _, y = (param.get("value", "") if param is not None else "").partition(",")
        try:
            offsets[asset.get("name", "")] = (int(x), int(y))
        except ValueError:
            continue
    # Mirrored aliases would need Habbo's flip rules, which are not known here, so they are skipped.
    aliases = {
        alias.get("name", ""): alias.get("link", "")
        for alias in manifest.iter("alias")
        if alias.get("fliph", "0") == "0" and alias.get("flipv", "0") == "0"
    }

    used: dict[str, set[int]] = {}
    still: list[list[dict[str, Any]]] = [[{"s": sprite.get("id", ""), "f": 0} for sprite in sprites]]
    for listed in frames or still:
        for part in listed:
            used.setdefault(str(part["s"]), set()).add(int(part["f"]))
    atlas = swf._Atlas()
    placed: dict[str, dict[str, int]] = {}
    described = []
    for sprite in sprites:
        sprite_id, member = sprite.get("id", ""), sprite.get("member", "")
        turns = sprite.get("directions", "0") == "1"
        for direction in range(8) if turns else [0]:
            for frame_number in used.get(sprite_id, set()):
                key = f"{member}_{direction}_{frame_number}"
                name = aliases.get(f"h_{key}", f"h_{key}")
                if name not in images or name not in offsets:
                    continue
                image = images[name]
                try:
                    left, top = atlas.add(image)
                except swf.SwfError:
                    return {"drawable": False, "why": ["too big"]}, None
                ox, oy = offsets[name]
                placed[key] = {"x": left, "y": top, "w": image.width, "h": image.height, "ox": ox, "oy": oy}
        described.append(
            {
                "id": sprite_id,
                "member": member,
                "add": sprite.get("ink") == INK_ADD,
                "turns": turns,
                "dirs": {
                    direction.get("id", "0"): {key: _int(direction, key) for key in ("dx", "dy", "dz")}
                    for direction in sprite.iter("direction")
                },
            }
        )
    if not placed:
        return {"drawable": False, "why": ["no images"]}, None
    return {"drawable": True, "sprites": described, "frames": frames, "images": placed}, atlas.render()


class Effects:
    def __init__(self, root: Path, upstream: Upstream) -> None:
        self.root = root
        self.upstream = upstream
        self._lock = threading.Lock()
        self._hotels: dict[str, tuple[float, tuple[str, str] | None]] = {}
        self._maps: dict[str, dict[int, str]] = {}
        self._file_lock = threading.Lock()

    def library(self, base: str, build_name: str, lib: str) -> bytes:
        """An effect's file, downloaded once and kept for both the room's layers and avatar drawing."""
        if not LIBRARY.fullmatch(lib):
            raise ValueError("Unexpected effect file name.")
        path = self.root / build_name / f"{lib}.swf"
        with self._file_lock:
            if path.exists():
                return path.read_bytes()
            body = self._fetch(f"{base}{lib}.swf", MAX_EFFECT_BYTES)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_bytes(body)
            temp.replace(path)
            return body

    def _fetch(self, url: str, limit: int) -> bytes:
        fetched = self.upstream.get(url, limit)
        if fetched.status != 200:
            raise UpstreamError(f"Unexpected effect response: HTTP {fetched.status}.")
        return fetched.body

    def _client(self, hotel: str) -> tuple[str, str] | None:
        checked, found = self._hotels.get(hotel, (0.0, None))
        wait = CHECK_SECONDS if found else RETRY_SECONDS
        if checked and time.monotonic() - checked < wait:
            return found
        try:
            found = client_folder(self.upstream, hotel)
        except (UpstreamError, ValueError, StopIteration) as exc:
            log.warning("Effect files are unavailable for %s: %s", hotel, exc)
            found = None
        self._hotels[hotel] = (time.monotonic(), found)
        return found

    def files(self, hotel: str, effect: int) -> tuple[Path, Path | None] | None:
        """The built manifest and sprite sheet for an effect, or None if Habbo has no such effect.

        Raises UpstreamError when Habbo cannot be reached.
        """
        with self._lock:
            client = self._client(hotel)
            if client is None:
                raise UpstreamError("Habbo's client files are unavailable.")
            base, build_name = client
            if build_name not in self._maps:
                self._maps = {build_name: parse_map(self._fetch(f"{base}effectmap.xml", MAX_MAP_BYTES))}
            lib = self._maps[build_name].get(effect)
            if lib is None:
                return None
            folder = self.root / build_name
            manifest, atlas = (
                folder / f"{lib}.v{EFFECT_VERSION}.json",
                folder / f"{lib}.v{EFFECT_VERSION}.png",
            )
            if not manifest.exists():
                try:
                    built, sheet = build(self.library(base, build_name, lib), lib)
                except (swf.SwfError, ET.ParseError) as exc:
                    log.warning("Effect %s could not be read: %s", lib, exc)
                    built, sheet = {"drawable": False, "why": ["unreadable"]}, None
                folder.mkdir(parents=True, exist_ok=True)
                if sheet is not None:
                    atlas.with_suffix(".tmp").write_bytes(sheet)
                    atlas.with_suffix(".tmp").replace(atlas)
                temp = manifest.with_suffix(".tmp")
                temp.write_text(json.dumps({"lib": lib, **built}), encoding="utf-8")
                temp.replace(manifest)
            return manifest, atlas if atlas.exists() else None
