"""Draws a Habbo avatar from its parts, using only the files Habbo's own client loads.

The rules come from Habbo's desktop client, which bundles HabboAvatarGeometry.xml and
HabboAvatarPartSets.xml. Looks come from figuredata, parts are found through figuremap.xml, and the
art comes from the hh_human_* libraries. Nothing is stored in the repo: every file is fetched on first
use and kept in the cache folder.

Poses, actions, gestures, signs and hand items are drawn from HabboAvatarActions.xml and the client's
animation file. Anything else returns None, and the caller asks Habbo's image service instead.
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
from PIL import Image, ImageChops

from wiredbench.config import HOTELS
from wiredbench.services import swf
from wiredbench.services.effects import parse_map
from wiredbench.services.handitems import CHECK_SECONDS, RETRY_SECONDS, client_folder
from wiredbench.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)

MAX_CLIENT_BYTES = 64 * 2**20
MAX_SWF_BYTES = 48 * 2**20
MAX_DATA_BYTES = 16 * 2**20
MAX_LIBRARY_BYTES = 16 * 2**20
CLIENT_KEY = "flash-windows"
CLIENT_FILE = "HabboAir.swf"
RULES = ("HabboAvatarGeometry", "HabboAvatarPartSets", "HabboAvatarAnimation")
ACTIONS_FILE = "HabboAvatarActions.xml"
ITEM_LIBRARY = "hh_human_item"
# Each geometry's canvas and where Habbo's offsets start on it, matching the image service.
CANVASES = {
    "vertical": ((64, 110), (0, 100)),
    "sitting": ((64, 110), (0, 100)),
    "horizontal": ((110, 64), (45, 52)),
}
MAX_LIBRARIES = 200
# Directions 4 to 6 are drawn as mirrored copies of 2 to 0.
MIRRORED = {4: 2, 5: 1, 6: 0}
UNTINTED = {"ey"}
# Measured against Habbo's images: its server draws the body art's 254 as 255.
BODY_LIBRARY = "hh_human_body"
MAX_ALIAS_HOPS = 6
# Raised when drawing changes, so avatars drawn before are drawn again.
FIGURE_RULES_VERSION = 3


@dataclass
class Action:
    """One avatar action from HabboAvatarActions.xml, such as sitting or waving."""

    id: str
    asset: str
    precedence: int
    geometry: str
    parts: str
    main: bool


# Body part ID to (x, z, radius, item types with their radius).
BodyParts = dict[str, tuple[float, float, float, list[tuple[str, float]]]]


@dataclass
class Rules:
    """How an avatar is put together, from the client's geometry, part set, animation and action files."""

    camera_z: float
    types: dict[str, BodyParts]
    head_parts: set[str]
    flipped: dict[str, str]
    removes: dict[str, str]
    active: dict[str, set[str]] = field(default_factory=dict)
    # Keyed by the name the image service uses, such as "wav" or "sit".
    actions: dict[str, Action] = field(default_factory=dict)
    # Action ID to part type to its frames, as (frame number, asset name part).
    frames: dict[str, dict[str, list[tuple[int, str | None]]]] = field(default_factory=dict)

    @property
    def parts(self) -> BodyParts:
        return self.types["vertical"]

    def posed(self, action_id: str, kind: str, frame: int) -> tuple[str, int] | None:
        """A part's art in another action, as an effect frame asks for a body part, such as "Sit"."""
        action = next((found for found in self.actions.values() if found.id == action_id), None)
        if action is None:
            return None
        frames = self.frames.get(action_id, {}).get(kind)
        if frames:
            number, asset = frames[frame % len(frames)]
            asset = action.asset if asset is None else asset
            return (asset, number) if asset else None
        return action.asset, 0

    def order(self, direction: int, head_direction: int, geometry: str = "vertical") -> list[str]:
        """Body parts from back to front."""
        parts = self.types.get(geometry, self.parts)

        def distance(part: str) -> float:
            x, z, radius, _ = parts[part]
            facing = head_direction if part in self.head_parts else direction
            angle = math.radians((45 * (facing + 1)) % 360)
            turned = x * math.sin(angle) + z * math.cos(angle)
            return min(abs(self.camera_z - turned - radius), abs(self.camera_z - turned + radius))

        return sorted(parts, key=distance, reverse=True)


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


def parse_rules(geometry: bytes, part_sets: bytes, animation: bytes = b"", actions: bytes = b"") -> Rules:
    root = safe_fromstring(geometry)
    camera = root.find("camera")
    camera_z = float(camera.findtext("z", "10")) if camera is not None else 10.0
    head_parts = {
        part.get("id", "")
        for avatar_set in root.iter("avatarset")
        if avatar_set.get("id") == "head"
        for part in avatar_set.iter("bodypart")
    }
    types: dict[str, BodyParts] = {}
    for geometry_type in root.iter("type"):
        parts: BodyParts = {}
        for part in geometry_type.findall("bodypart"):
            items = [(item.get("id", ""), float(item.get("radius", "0"))) for item in part.findall("item")]
            if items:
                parts[part.get("id", "")] = (
                    float(part.get("x", "0")),
                    float(part.get("z", "0")),
                    float(part.get("radius", "0")),
                    items,
                )
        types[geometry_type.get("id", "")] = parts
    sets = safe_fromstring(part_sets)
    flipped: dict[str, str] = {}
    removes: dict[str, str] = {}
    for part in sets.iter("part"):
        set_type = part.get("set-type", "")
        if part.get("flipped-set-type"):
            flipped[set_type] = part.get("flipped-set-type", "")
        if part.get("remove-set-type"):
            removes[set_type] = part.get("remove-set-type", "")
    active = {
        group.get("id", ""): {part.get("set-type", "") for part in group.iter("activePart")}
        for group in sets.iter("activePartSet")
    }
    rules = Rules(camera_z, types, head_parts, flipped, removes, active)
    if actions:
        add_actions(rules, actions)
    if animation:
        for action in safe_fromstring(animation).iter("action"):
            animated: dict[str, list[tuple[int, str | None]]] = {}
            for part in action.findall("part"):
                frames: list[tuple[int, str | None]] = []
                # The image service counts each listed frame once, whatever its repeats say.
                for frame in part.findall("frame"):
                    frames.append((int(frame.get("number", "0")), frame.get("assetpartdefinition")))
                animated[part.get("set-type", "")] = frames
            rules.frames[action.get("id", "")] = animated
    return rules


def add_actions(rules: Rules, body: bytes) -> None:
    """Adds the actions from HabboAvatarActions.xml, which sits in the client folder rather than the client."""
    for action in safe_fromstring(body).iter("action"):
        asset = action.get("assetpartdefinition", "")
        found = Action(
            action.get("id", ""),
            asset,
            int(action.get("precedence", "1000")),
            action.get("geometrytype", "vertical"),
            action.get("activepartset", ""),
            action.get("main") == "1",
        )
        # The image service names an action by its art. Several actions reuse "std" art, so the
        # default action alone answers to "std".
        if action.get("isdefault") == "1":
            rules.actions["std"] = found
        elif asset not in ("std", "USE_PARAMETER"):
            rules.actions.setdefault(asset, found)


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

    def find(self, stem: str, frame: int) -> tuple[Image.Image, tuple[int, int]] | None:
        """A frame of an asset, or its first frame when the asset has only one."""
        return self.asset(f"{stem}_{frame}") or self.asset(f"{stem}_0")

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
    offsets: dict[str, tuple[int, int]] = {}
    aliases: dict[str, str] = {}
    for binary in parsed.binaries.values():
        if b"<manifest" not in binary[:400]:
            continue
        manifest = safe_fromstring(binary)
        for asset in manifest.iter("asset"):
            offsets.setdefault(
                asset.get("name", ""), (0, 0)
            )  # Art listed without an offset sits at the origin.
            for param in asset.iter("param"):
                if param.get("key") == "offset":
                    x, _, y = param.get("value", "").partition(",")
                    with contextlib.suppress(ValueError):
                        offsets[asset.get("name", "")] = (int(x), int(y))
        for alias in manifest.iter("alias"):
            if alias.get("fliph", "0") == "0" and alias.get("flipv", "0") == "0":
                aliases[alias.get("name", "")] = alias.get("link", "")
    return Library(images, offsets, aliases)


@dataclass
class EffectFrame:
    """What one frame of an effect does to the avatar."""

    library: str
    removes: set[str]
    # Body part ID to (action ID or None, frame, dx, dy, direction change).
    body: dict[str, tuple[str | None, int, int, int, int]]
    # Added part: (part type, body part it attaches to, frame, dx, dy, effect art name or "").
    adds: list[tuple[str, str, int, int, int, str]]
    # Part type to the effect art drawn in its place, such as a helmet for a hat.
    swaps: dict[str, str] = field(default_factory=dict)


@dataclass
class EffectSprite:
    member: str
    add: bool
    turns: bool
    # Direction to (dz, dx, dy).
    directions: dict[int, tuple[int, int, int]]


@dataclass
class EffectAnimation:
    """An effect from its own file: parts it removes or adds, sprites, recolouring and frames."""

    library: str
    removes: set[str]
    # Added part ID to (body part it attaches to, effect art name or "").
    adds: dict[str, tuple[str, str]]
    sprites: dict[str, EffectSprite]
    lifts: bool
    turn: int
    recolour: tuple[int, str, str] | None
    # Each frame: sprite or add ID to (frame, dx, dy, direction change), and body parts.
    frames: list[
        tuple[
            dict[str, tuple[int, int, int, int]],
            dict[str, tuple[str | None, int, int, int, int]],
            dict[str, str],
        ]
    ]

    def frame(self, number: int) -> EffectFrame:
        sprites, body, swaps = self.frames[number % len(self.frames)] if self.frames else ({}, {}, {})
        adds = [
            (kind, align, *sprites.get(base or kind, sprites.get(kind, (0, 0, 0, 0)))[:3], base)
            for kind, (align, base) in self.adds.items()
        ]
        return EffectFrame(self.library, self.removes, body, adds, swaps)

    def sprite_frames(self, number: int) -> dict[str, tuple[int, int, int, int]]:
        if self.frames:
            return self.frames[number % len(self.frames)][0]
        return dict.fromkeys(self.sprites, (0, 0, 0, 0))


def parse_effect(data: bytes, name: str) -> tuple[Library, EffectAnimation] | None:
    """An effect's art and animation, or None for a file without one."""
    library = parse_library(data, name)
    animation = next(
        (
            safe_fromstring(binary)
            for binary in swf.parse(data).binaries.values()
            if b"<animation" in binary[:400]
        ),
        None,
    )
    if animation is None:
        return None
    if animation.tag != "animation":
        animation = next(animation.iter("animation"), animation)

    def number(element: ET.Element, key: str) -> int:
        try:
            return int(element.get(key, "0") or 0)
        except ValueError:
            return 0

    sprites = {}
    lifts = False
    for sprite in animation.findall("sprite"):
        if sprite.get("id") == "avatar":
            lifts = True
            continue
        sprites[sprite.get("id", "")] = EffectSprite(
            sprite.get("member", ""),
            sprite.get("ink") == "33",
            sprite.get("directions") == "1",
            {
                number(direction, "id"): (
                    number(direction, "dz"),
                    number(direction, "dx"),
                    number(direction, "dy"),
                )
                for direction in sprite.findall("direction")
            },
        )
    recolour = None
    avatar = animation.find("avatar")
    if avatar is not None:
        recolour = (number(avatar, "ink"), avatar.get("foreground", ""), avatar.get("background", ""))
    turn = next((number(direction, "offset") for direction in animation.findall("direction")), 0)
    frames = []
    for frame in animation.iter("frame"):
        shown = {
            part.get("id", ""): (
                number(part, "frame"),
                number(part, "dx"),
                number(part, "dy"),
                number(part, "dd"),
            )
            for part in frame.findall("fx")
        }
        body = {
            part.get("id", ""): (
                part.get("action"),
                number(part, "frame"),
                number(part, "dx"),
                number(part, "dy"),
                number(part, "dd"),
            )
            for part in frame.findall("bodypart")
        }
        swaps = {
            item.get("id", ""): item.get("base", "")
            for part in frame.findall("bodypart")
            for item in part.findall("item")
            if item.get("base")
        }
        frames.extend([(shown, body, swaps)] * max(1, number(frame, "repeats")))
    return library, EffectAnimation(
        name,
        {remove.get("id", "") for remove in animation.findall("remove")},
        {add.get("id", ""): (add.get("align", ""), add.get("base", "")) for add in animation.findall("add")},
        sprites,
        lifts,
        turn,
        recolour,
        frames,
    )


@dataclass
class Pose:
    """Which art each part shows for an action string such as "sit,wav,crr=12"."""

    geometry: str
    actions: list[Action]
    items: list[tuple[str, str]]
    frame: int

    def shows(self, rules: Rules, kind: str) -> tuple[str, int] | None:
        """The art name part and frame number for a part type, or None when it is not drawn."""
        for action in self.actions:
            if kind not in rules.active.get(action.parts, set()):
                continue
            animated = rules.frames.get(action.id, {})
            frames = animated.get(kind)
            # An action on top of the pose, such as talking, changes only the parts its animation lists.
            if animated and not frames and not action.main and action.asset != "std":
                continue
            if frames:
                number, asset = frames[self.frame % len(frames)]
                asset = action.asset if asset is None else asset
                return (asset, number) if asset else None  # An empty name hides the part for that frame.
            return action.asset, 0
        return None


def pose(rules: Rules, action: str, gesture: str, frame: int) -> Pose | None:
    """None for an action or gesture this does not know, so the image service draws it instead."""
    chosen, items = [], []
    for token in action.split(","):
        name, _, value = token.partition("=")
        found = rules.actions.get(name)
        if found is None or (value and not value.isdigit()):
            return None
        chosen.append(found)
        if value:
            items.append(("li" if name == "sig" else "ri", value))
    if gesture != "std":
        found = rules.actions.get(gesture)
        if found is None:
            return None
        chosen.append(found)
    if "std" in rules.actions:
        chosen.append(rules.actions["std"])
    chosen.sort(key=lambda found: found.precedence)
    main = next((found for found in chosen if found.main), None)
    return Pose(main.geometry if main else "vertical", chosen, items, frame)


def compose(
    rules: Rules,
    looks: list[Look],
    library: dict[str, Library],
    direction: int,
    head_direction: int,
    shown: Pose | None = None,
    effect: EffectFrame | None = None,
) -> Image.Image:
    """The avatar in a pose, on the same canvas as Habbo's image service. Standing still by default.

    An effect frame can remove parts, add its own parts, and pose, move or turn whole body parts.
    """
    shown = shown or pose(rules, "std", "std", 0) or Pose("vertical", [], [], 0)
    # Measured against Habbo's images: lying only faces 2 or 4, and sitting only straight. The image
    # service draws a lying avatar facing any other way as facing 4, and sits a diagonal one facing 4.
    if shown.geometry == "horizontal" and direction not in (2, 4):
        direction = head_direction = 4
    elif shown.geometry == "sitting" and direction % 2:
        direction, head_direction = 4, 5 if head_direction in (1, 5) else head_direction
    size, origin = CANVASES.get(shown.geometry, CANVASES["vertical"])
    hidden = {kind for look in looks for kind in look.hidden}
    # Part type to (library, part ID, colour, name its art goes by when it is not the part type).
    worn: dict[str, list[tuple[str, str, str | None, str]]] = {}
    for look in looks:
        for kind, part_id, color, library_name in look.parts:
            if kind not in hidden and library_name:
                worn.setdefault(kind, []).append((library_name, part_id, color, ""))
    for kind, item_id in shown.items:
        worn.setdefault(kind, []).append((ITEM_LIBRARY, item_id, None, ""))
    for kind, removed in rules.removes.items():
        if kind in worn:
            worn.pop(removed, None)
    parts = dict(rules.types.get(shown.geometry, rules.parts))
    if effect:
        for kind in effect.removes:
            worn.pop(kind, None)
        for kind, body_part, *_, base in effect.adds:
            if body_part in parts:
                x, z, radius, items = parts[body_part]
                if all(item != kind for item, _ in items):
                    parts[body_part] = (x, z, radius, [*items, (kind, 1.0)])  # On top within its body part.
                worn[kind] = [(effect.library, "1", None, base)]
        for kind, base in effect.swaps.items():
            worn[kind] = [(effect.library, "1", None, base)]
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for body_part in rules.order(direction, head_direction, shown.geometry):
        if body_part not in parts:
            continue
        facing = head_direction if body_part in rules.head_parts else direction
        moved = effect.body.get(body_part) if effect else None
        shift_x = shift_y = 0
        if moved:
            facing = (facing + moved[4]) % 8
            shift_x, shift_y = moved[2], moved[3]
        mirrored = facing in MIRRORED
        art_direction = MIRRORED.get(facing, facing)
        # Parts drawn later are nearer: a larger radius is nearer the camera.
        for kind, _ in sorted(parts[body_part][3], key=lambda item: item[1]):
            art = shown.shows(rules, kind) if rules.actions else ("std", 0)
            added = next((add for add in effect.adds if add[0] == kind), None) if effect else None
            if added:
                art = ("std", added[2])
                shift_x, shift_y = (moved[2], moved[3]) if moved else (0, 0)
                shift_x, shift_y = shift_x + added[3], shift_y + added[4]
            elif moved and moved[0] is not None:
                art = rules.posed(moved[0], kind, moved[1]) or art
            if art is None:
                continue
            asset, number = art
            for library_name, part_id, color, base in worn.get(kind, []):
                if base:  # Effect art, which has no pose or action art of its own.
                    asset, number = "std", added[2] if added else 0
                lib = library.get(library_name)
                if lib is None:
                    continue
                flip = mirrored
                # Art made for this very direction is used as it is. Actions and items have some.
                found = mirrored and lib.find(f"h_{asset}_{base or kind}_{part_id}_{facing}", number)
                if found:
                    flip = False
                else:
                    named = base or (rules.flipped.get(kind, kind) if mirrored else kind)
                    found = lib.find(f"h_{asset}_{named}_{part_id}_{art_direction}", number)
                    # An action without art for a part, such as the head while blowing a kiss, shows it
                    # standing.
                    if not found and asset != "std":
                        found = lib.find(f"h_std_{named}_{part_id}_{art_direction}", 0)
                if not found:
                    continue
                image, (offset_x, offset_y) = found
                if color and kind not in UNTINTED and color.upper() != "FFFFFF":
                    image = tint(image, color)
                left, top = origin[0] - offset_x, origin[1] - offset_y + shift_y
                if flip:
                    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    left = size[0] - left - image.width - shift_x
                else:
                    left += shift_x
                layer = Image.new("RGBA", size, (0, 0, 0, 0))
                layer.paste(image, (left, top))
                canvas = Image.alpha_composite(canvas, layer)
    return canvas


# Room around a plain avatar for what an effect adds: lifts of up to 75 pixels, wide boards and wings.
EFFECT_MARGIN = (16, 90, 10)


def recolour(image: Image.Image, ink: int, foreground: str, background: str) -> Image.Image:
    """Turns the avatar into shades between two colours, as Ice and Ghost do. Not checked in a room yet.

    Dark art takes the background colour and light art the foreground. Ink 37 also halves the opacity.
    """

    def colour(text: str) -> tuple[int, int, int, int | None]:
        text = text.lstrip("#")
        alpha = int(text[:2], 16) if len(text) == 8 else None
        rgb = int(text[-6:], 16) if text else 0
        return (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, alpha

    try:
        fr, fg, fb, fa = colour(foreground)
        br, bg, bb, ba = colour(background)
    except ValueError:
        return image
    gray = image.convert("L")
    red = gray.point([round(br + (fr - br) * v / 255) for v in range(256)])
    green = gray.point([round(bg + (fg - bg) * v / 255) for v in range(256)])
    blue = gray.point([round(bb + (fb - bb) * v / 255) for v in range(256)])
    alpha = image.getchannel("A")
    if fa is not None and ba is not None:
        scale = gray.point([round(ba + (fa - ba) * v / 255) for v in range(256)])
        alpha = Image.composite(scale, alpha, alpha.point(lambda v: 255 if v else 0))
    if ink == 37:
        alpha = alpha.point(lambda v: v // 2)
    return Image.merge("RGBA", (red, green, blue, alpha))


def as_light(image: Image.Image) -> Image.Image:
    """A sprite drawn with ink 33, which adds its light, made see-through where it is dark.

    Such art often sits on black, which adds nothing in Habbo but would show as black on a clear canvas.
    """
    rgba = image.convert("RGBA")
    premultiplied = [ImageChops.multiply(band, rgba.getchannel("A")) for band in rgba.convert("RGB").split()]
    alpha = ImageChops.lighter(ImageChops.lighter(premultiplied[0], premultiplied[1]), premultiplied[2])
    rgb = []
    for band in premultiplied:
        pixels = [
            min(255, round(value * 255 / level)) if level else 0
            for value, level in zip(band.getdata(), alpha.getdata(), strict=True)
        ]
        out = Image.new("L", band.size)
        out.putdata(pixels)
        rgb.append(out)
    return Image.merge("RGBA", (*rgb, alpha))


def compose_effect(
    rules: Rules,
    looks: list[Look],
    library: dict[str, Library],
    direction: int,
    head_direction: int,
    shown: Pose,
    animation: EffectAnimation,
    frame: int,
) -> Image.Image:
    """An avatar with an effect, on a canvas with EFFECT_MARGIN added around the plain avatar's."""
    turned, turned_head = (direction + animation.turn) % 8, (head_direction + animation.turn) % 8
    effect = animation.frame(frame)
    avatar = compose(rules, looks, library, turned, turned_head, shown, effect)
    if animation.recolour:
        avatar = recolour(avatar, *animation.recolour)
    margin_x, margin_top, margin_bottom = EFFECT_MARGIN
    width, height = avatar.size
    canvas = Image.new("RGBA", (width + 2 * margin_x, height + margin_top + margin_bottom), (0, 0, 0, 0))
    origin = CANVASES.get(shown.geometry, CANVASES["vertical"])[1]
    shown_sprites = animation.sprite_frames(frame)
    lift = shown_sprites.get("avatar", (0, 0, 0, 0)) if animation.lifts else (0, 0, 0, 0)
    layers: list[tuple[int, Image.Image, int, int, bool]] = []
    effect_art = library[animation.library]
    for sprite_id, (number, dx, dy, dd) in shown_sprites.items():
        sprite = animation.sprites.get(sprite_id)
        if sprite is None:
            continue
        facing = (turned + dd) % 8 if sprite.turns else 0
        dz, sx, sy = sprite.directions.get(facing, (0, 0, 0))
        found = effect_art.find(f"h_{sprite.member}_{facing}", number)
        flip = False
        if not found and facing in MIRRORED:
            found, flip = effect_art.find(f"h_{sprite.member}_{MIRRORED[facing]}", number), True
        if not found:
            continue
        image, (offset_x, offset_y) = found
        left = origin[0] - offset_x + sx + dx
        if flip:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            left = width - left - image.width
        layers.append((dz, image, margin_x + left, margin_top + origin[1] - offset_y + sy + dy, sprite.add))
    layers.append((0, avatar, margin_x + lift[1], margin_top + lift[2], False))
    # Sprites with a negative depth are behind the avatar. The avatar comes before sprites at depth 0.
    for _, image, left, top, light in sorted(layers, key=lambda layer: (layer[0], layer[1] is not avatar)):
        if light:
            image = as_light(image)
        canvas.alpha_composite(image, (max(0, left), max(0, top)), (max(0, -left), max(0, -top)))
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
        self._effects: dict[int, EffectAnimation | None] = {}
        self._effect_map: dict[int, str] = {}

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
        rules = parse_rules(paths[0].read_bytes(), paths[1].read_bytes(), paths[2].read_bytes())
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

    def _effect(self, base: str, build: str, effect: int) -> EffectAnimation | None:
        """An effect's animation, with its art added to the libraries. None when Habbo has no such effect."""
        if effect not in self._effects:
            name = self._effect_map.get(effect)
            found = None
            if name:
                data = self._cached(self.root / build / f"{name}.swf", f"{base}{name}.swf", MAX_LIBRARY_BYTES)
                parsed = parse_effect(data, name)
                if parsed:
                    self._libraries[name], found = parsed
            self._effects[effect] = found
        return self._effects[effect]

    def draw(
        self,
        hotel: str,
        figure: str,
        direction: int,
        head_direction: int,
        action: str = "std",
        gesture: str = "std",
        frame: int = 0,
        effect: int | None = None,
    ) -> bytes | None:
        """A PNG of the avatar, or None when it cannot be drawn here.

        With an effect, frame is the effect's frame, and the canvas has EFFECT_MARGIN around it.
        """
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
                    self._effects = {}
                    self._effect_map = parse_map(
                        self._cached(
                            self.root / build / "effectmap.xml", f"{base}effectmap.xml", MAX_DATA_BYTES
                        )
                    )
                    rules.actions = {}
                if not rules.actions:
                    add_actions(
                        rules,
                        self._cached(
                            self.root / build / ACTIONS_FILE, f"{base}{ACTIONS_FILE}", MAX_DATA_BYTES
                        ),
                    )
                data, mapping = self._data[build]
                looks = resolve(figure, data, mapping)
                shown = pose(rules, action, gesture, frame)
                if looks is None or shown is None:
                    return None
                needed = {library for look in looks for *_, library in look.parts if library}
                if shown.items:
                    needed.add(ITEM_LIBRARY)
                for name in needed - set(self._libraries):
                    if not name.replace("_", "").isalnum() or len(self._libraries) > MAX_LIBRARIES:
                        return None
                    swf_data = self._cached(
                        self.root / build / f"{name}.swf", f"{base}{name}.swf", MAX_LIBRARY_BYTES
                    )
                    self._libraries[name] = parse_library(swf_data, name)
                animation = None
                if effect is not None:
                    animation = self._effect(base, build, effect)
                    if animation is None:
                        return None
                if animation:
                    image = compose_effect(
                        rules, looks, self._libraries, direction, head_direction, shown, animation, frame
                    )
                else:
                    image = compose(rules, looks, self._libraries, direction, head_direction, shown)
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
