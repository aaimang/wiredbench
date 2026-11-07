"""Draws a Habbo avatar from its parts, using only the files Habbo's own client loads.

The rules come from Habbo's desktop client, which bundles HabboAvatarGeometry.xml and
HabboAvatarPartSets.xml. Looks come from figuredata, parts are found through figuremap.xml, and the
art comes from the hh_human_* libraries. Nothing is stored in the repo: every file is fetched on first
use and kept in the cache folder.

Only still, standing avatars are drawn for now. Anything else returns None, and the caller asks
Habbo's image service instead.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import threading
import time
import xml.etree.ElementTree as ET  # noqa: S405 - Only for the error type. defusedxml does the parsing.
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml.ElementTree import fromstring as safe_fromstring
from PIL import Image

from wiredbench.config import HOTELS
from wiredbench.services import swf
from wiredbench.services.handitems import CHECK_SECONDS, RETRY_SECONDS, client_folder
from wiredbench.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)

MAX_CLIENT_BYTES = 64 * 2**20
MAX_SWF_BYTES = 48 * 2**20
MAX_DATA_BYTES = 16 * 2**20
MAX_LIBRARY_BYTES = 16 * 2**20
CLIENT_KEY = "flash-windows"
CLIENT_FILE = "HabboAir.swf"
RULES = ("HabboAvatarGeometry", "HabboAvatarPartSets")
MAX_LIBRARIES = 200
CANVAS = (64, 110)
ORIGIN = (0, 100)
# Directions 4 to 6 are drawn as mirrored copies of 2 to 0.
MIRRORED = {4: 2, 5: 1, 6: 0}
UNTINTED = {"ey"}
# Measured against Habbo's images: its server draws the body art's 254 as 255.
BODY_LIBRARY = "hh_human_body"
MAX_ALIAS_HOPS = 6


@dataclass
class Rules:
    """How the parts of an avatar stack, from the client's geometry and part set files."""

    camera_z: float
    # Body part ID to (x, z, radius, item types with their radius), for the standing pose.
    parts: dict[str, tuple[float, float, float, list[tuple[str, float]]]]
    head_parts: set[str]
    flipped: dict[str, str]
    removes: dict[str, str]

    def order(self, direction: int, head_direction: int) -> list[str]:
        """Body parts from back to front."""

        def distance(part: str) -> float:
            x, z, radius, _ = self.parts[part]
            facing = head_direction if part in self.head_parts else direction
            angle = math.radians((45 * (facing + 1)) % 360)
            turned = x * math.sin(angle) + z * math.cos(angle)
            return min(abs(self.camera_z - turned - radius), abs(self.camera_z - turned + radius))

        return sorted(self.parts, key=distance, reverse=True)


@dataclass
class Look:
    """One worn set: its parts with their colours, and the part types it hides."""

    # Part type, part ID, colour, and the library holding its art.
    parts: list[tuple[str, str, str | None, str | None]] = field(default_factory=list)
    hidden: set[str] = field(default_factory=set)


@dataclass
class FigureData:
    # Set type to (palette ID, set ID to (parts, hidden layers)).
    sets: dict[str, tuple[str, dict[str, tuple[list[tuple[str, str, int, bool]], set[str]]]]]
    palettes: dict[str, dict[str, str]]


def parse_rules(geometry: bytes, part_sets: bytes) -> Rules:
    root = safe_fromstring(geometry)
    camera = root.find("camera")
    camera_z = float(camera.findtext("z", "10")) if camera is not None else 10.0
    head_parts = {
        part.get("id", "")
        for avatar_set in root.iter("avatarset")
        if avatar_set.get("id") == "head"
        for part in avatar_set.iter("bodypart")
    }
    vertical = next(kind for kind in root.iter("type") if kind.get("id") == "vertical")
    parts = {}
    for part in vertical.findall("bodypart"):
        items = [(item.get("id", ""), float(item.get("radius", "0"))) for item in part.findall("item")]
        if items:
            parts[part.get("id", "")] = (
                float(part.get("x", "0")),
                float(part.get("z", "0")),
                float(part.get("radius", "0")),
                items,
            )
    sets = safe_fromstring(part_sets)
    flipped, removes = {}, {}
    for part in sets.iter("part"):
        kind = part.get("set-type", "")
        if part.get("flipped-set-type"):
            flipped[kind] = part.get("flipped-set-type", "")
        if part.get("remove-set-type"):
            removes[kind] = part.get("remove-set-type", "")
    return Rules(camera_z, parts, head_parts, flipped, removes)


def parse_figuredata(body: bytes) -> FigureData:
    root = safe_fromstring(body)
    palettes = {
        palette.get("id", ""): {
            color.get("id", ""): (color.text or "").strip() for color in palette.iter("color")
        }
        for palette in root.iter("palette")
    }
    sets: dict[str, tuple[str, dict[str, tuple[list[tuple[str, str, int, bool]], set[str]]]]] = {}
    for set_type in root.iter("settype"):
        found = {}
        for worn in set_type.iter("set"):
            parts = [
                (
                    part.get("type", ""),
                    part.get("id", ""),
                    int(part.get("colorindex", "0") or 0),
                    part.get("colorable", "0") == "1",
                )
                for part in worn.findall("part")
            ]
            hidden = {layer.get("parttype", "") for layer in worn.iter("layer")}
            found[worn.get("id", "")] = (parts, hidden)
        sets[set_type.get("type", "")] = (set_type.get("paletteid", ""), found)
    return FigureData(sets, palettes)


def parse_figuremap(body: bytes) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for library in safe_fromstring(body).iter("lib"):
        for part in library.iter("part"):
            found.setdefault((part.get("type", ""), part.get("id", "")), library.get("id", ""))
    return found


def resolve(figure: str, data: FigureData, libraries: dict[tuple[str, str], str]) -> list[Look] | None:
    """The worn sets of a figure string, or None if it names something figuredata lacks."""
    looks = []
    for token in figure.split("."):
        kind, _, rest = token.partition("-")
        set_id, *colors = rest.split("-")
        if kind not in data.sets or set_id not in data.sets[kind][1]:
            return None
        palette_id, sets = data.sets[kind]
        palette = data.palettes.get(palette_id, {})
        parts, hidden = sets[set_id]
        known = [libraries[(part, part_id)] for part, part_id, _, _ in parts if (part, part_id) in libraries]
        look = Look(hidden=set(hidden))
        for part, part_id, color_index, colorable in parts:
            color = None
            if colorable and 0 < color_index <= len(colors):
                color = palette.get(colors[color_index - 1])
            # figuremap misses some parts. Habbo still draws them, from the set's other library.
            look.parts.append(
                (part, part_id, color, libraries.get((part, part_id)) or (known[0] if known else None))
            )
        looks.append(look)
    return looks


def tint(image: Image.Image, color: str) -> Image.Image:
    """Multiplies the art by a palette colour, rounding as Habbo's own images do."""
    try:
        r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return image
    table = [round(v * c / 255) for c in (r, g, b) for v in range(256)] + list(range(256))
    return image.point(table)


@dataclass
class Library:
    images: dict[str, Image.Image]
    offsets: dict[str, tuple[int, int]]
    aliases: dict[str, str]

    def asset(self, name: str) -> tuple[Image.Image, tuple[int, int]] | None:
        for _ in range(MAX_ALIAS_HOPS):
            if name in self.images and name in self.offsets:
                return self.images[name], self.offsets[name]
            if name not in self.aliases:
                return None
            name = self.aliases[name]
        return None


def parse_library(data: bytes, name: str) -> Library:
    parsed = swf.parse(data)
    images = {}
    for full, image in parsed.named_images().items():
        key = full[len(name) + 1 :] if full.startswith(f"{name}_") else full
        image = image.convert("RGBA")
        if name == BODY_LIBRARY:
            image = image.point([255 if v == 254 else v for v in range(256)] * 3 + list(range(256)))
        images[key] = image
    offsets, aliases = {}, {}
    for binary in parsed.binaries.values():
        if b"<manifest" not in binary[:400]:
            continue
        manifest = safe_fromstring(binary)
        for asset in manifest.iter("asset"):
            for param in asset.iter("param"):
                if param.get("key") == "offset":
                    x, _, y = param.get("value", "").partition(",")
                    with contextlib.suppress(ValueError):
                        offsets[asset.get("name", "")] = (int(x), int(y))
        for alias in manifest.iter("alias"):
            if alias.get("fliph", "0") == "0" and alias.get("flipv", "0") == "0":
                aliases[alias.get("name", "")] = alias.get("link", "")
    return Library(images, offsets, aliases)


def compose(
    rules: Rules,
    looks: list[Look],
    library: dict[str, Library],
    direction: int,
    head_direction: int,
) -> Image.Image:
    """The avatar standing still, on the same 64x110 canvas as Habbo's image service."""
    hidden = {kind for look in looks for kind in look.hidden}
    worn: dict[str, list[tuple[str, str, str | None]]] = {}
    for look in looks:
        for kind, part_id, color, library_name in look.parts:
            if kind not in hidden and library_name:
                worn.setdefault(kind, []).append((library_name, part_id, color))
    for kind, removed in rules.removes.items():
        if kind in worn:
            worn.pop(removed, None)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for body_part in rules.order(direction, head_direction):
        facing = head_direction if body_part in rules.head_parts else direction
        mirrored = facing in MIRRORED
        art_direction = MIRRORED.get(facing, facing)
        # Parts drawn later are nearer: a larger radius is nearer the camera.
        for kind, _ in sorted(rules.parts[body_part][3], key=lambda item: item[1]):
            for library_name, part_id, color in worn.get(kind, []):
                shown = rules.flipped.get(kind, kind) if mirrored else kind
                found = library[library_name].asset(f"h_std_{shown}_{part_id}_{art_direction}_0")
                if found is None:
                    continue
                image, (offset_x, offset_y) = found
                if color and kind not in UNTINTED and color.upper() != "FFFFFF":
                    image = tint(image, color)
                left, top = ORIGIN[0] - offset_x, ORIGIN[1] - offset_y
                if mirrored:
                    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    left = CANVAS[0] - left - image.width
                layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
                layer.paste(image, (left, top))
                canvas = Image.alpha_composite(canvas, layer)
    return canvas


class Figures:
    def __init__(self, root: Path, upstream: Upstream) -> None:
        self.root = root
        self.upstream = upstream
        self._lock = threading.Lock()
        self._hotels: dict[str, tuple[float, tuple[str, str] | None]] = {}
        self._rules: tuple[str, Rules] | None = None
        self._rules_checked = 0.0
        self._data: dict[str, tuple[FigureData, dict[tuple[str, str], str]]] = {}
        self._libraries: dict[str, Library] = {}

    def _fetch(self, url: str, limit: int) -> bytes:
        fetched = self.upstream.get(url, limit)
        if fetched.status != 200:
            raise UpstreamError(f"Unexpected figure file response: HTTP {fetched.status}.")
        return fetched.body

    def _client_rules(self, hotel: str) -> Rules:
        # Which client is current is checked once a day, like the other Habbo files.
        if self._rules and time.monotonic() - self._rules_checked < CHECK_SECONDS:
            return self._rules[1]
        self._rules_checked = time.monotonic()
        urls = json.loads(self._fetch(f"https://{HOTELS[hotel]}/gamedata/clienturls", 2**20))
        url, version = str(urls[CLIENT_KEY]), str(urls.get(f"{CLIENT_KEY}-version", ""))
        key = url.rstrip("/").rsplit("/", 2)[-2]
        if not key.replace("_", "").isalnum():
            raise ValueError("Unexpected client folder.")
        if self._rules and self._rules[0] == key:
            return self._rules[1]
        folder = self.root / "client" / key
        paths = [folder / f"{name}.xml" for name in RULES]
        if not all(path.exists() for path in paths):
            with zipfile.ZipFile(io.BytesIO(self._fetch(url, MAX_CLIENT_BYTES))) as archive:
                if archive.getinfo(CLIENT_FILE).file_size > MAX_SWF_BYTES:
                    raise ValueError("The client is larger than expected.")
                parsed = swf.parse(archive.read(CLIENT_FILE))
            found = {
                name: data
                for key_id, data in parsed.binaries.items()
                for symbol in parsed.symbols.get(key_id, [])
                for name in RULES
                if symbol.startswith(f"{name}_xml")
            }
            if set(found) != set(RULES):
                raise ValueError("The client has no avatar rules.")
            folder.mkdir(parents=True, exist_ok=True)
            for name, path in zip(RULES, paths, strict=True):
                path.write_bytes(found[name])
            log.info("Read avatar rules from Habbo client %s.", version or key)
        rules = parse_rules(paths[0].read_bytes(), paths[1].read_bytes())
        self._rules = (key, rules)
        return rules

    def _client(self, hotel: str) -> tuple[str, str] | None:
        checked, found = self._hotels.get(hotel, (0.0, None))
        if checked and time.monotonic() - checked < (CHECK_SECONDS if found else RETRY_SECONDS):
            return found
        try:
            found = client_folder(self.upstream, hotel)
        except (UpstreamError, ValueError, StopIteration) as exc:
            log.warning("Figure files are unavailable for %s: %s", hotel, exc)
            found = None
        self._hotels[hotel] = (time.monotonic(), found)
        return found

    def _cached(self, path: Path, url: str, limit: int) -> bytes:
        if path.exists():
            return path.read_bytes()
        body = self._fetch(url, limit)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(body)
        temp.replace(path)
        return body

    def draw(self, hotel: str, figure: str, direction: int, head_direction: int) -> bytes | None:
        """A PNG of the avatar standing still, or None when it cannot be drawn here."""
        with self._lock:
            try:
                client = self._client(hotel)
                if client is None:
                    return None
                base, build = client
                rules = self._client_rules(hotel)
                if build not in self._data:
                    folder = self.root / build
                    data = parse_figuredata(
                        self._cached(
                            folder / f"figuredata-{hotel}.xml",
                            f"https://{HOTELS[hotel]}/gamedata/figuredata/1",
                            MAX_DATA_BYTES,
                        )
                    )
                    mapping = parse_figuremap(
                        self._cached(folder / "figuremap.xml", f"{base}figuremap.xml", MAX_DATA_BYTES)
                    )
                    self._data = {build: (data, mapping)}
                    self._libraries = {}
                data, mapping = self._data[build]
                looks = resolve(figure, data, mapping)
                if looks is None:
                    return None
                needed = {library for look in looks for *_, library in look.parts if library}
                for name in needed - set(self._libraries):
                    if not name.replace("_", "").isalnum() or len(self._libraries) > MAX_LIBRARIES:
                        return None
                    swf_data = self._cached(
                        self.root / build / f"{name}.swf", f"{base}{name}.swf", MAX_LIBRARY_BYTES
                    )
                    self._libraries[name] = parse_library(swf_data, name)
                image = compose(rules, looks, self._libraries, direction, head_direction)
            except (
                UpstreamError,
                ValueError,
                KeyError,
                StopIteration,
                ET.ParseError,
                swf.SwfError,
                OSError,
            ) as exc:
                log.warning("Could not draw %s from its parts: %s", figure, exc)
                return None
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue()
