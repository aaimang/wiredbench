"""Turns a Habbo furni SWF into a sprite atlas and a JSON manifest, with no Flash tooling.

A SWF comes from outside, so it is treated as hostile: every read is bounds-checked, decompression and
image sizes are limited, XML goes through defusedxml, and any parsing failure becomes SwfError.
"""

from __future__ import annotations

import io
import re
import struct
import xml.etree.ElementTree as ET  # noqa: S405 - Only for types and for walking trees defusedxml parsed.
import zlib
from dataclasses import dataclass, field
from typing import Any

from defusedxml.ElementTree import fromstring as safe_fromstring
from PIL import Image, UnidentifiedImageError

MAX_SWF_BYTES = 32 * 2**20
MAX_IMAGE_PIXELS = 4096 * 4096
MAX_TOTAL_PIXELS = 8192 * 8192
ATLAS_WIDTH = 1024
MAX_ATLAS_HEIGHT = 8192
SIZE = 64
SHADOW_ALPHA = 48
BELOW_EVERYTHING = -9999

TAG_END = 0
TAG_LOSSLESS = 20
TAG_JPEG2 = 21
TAG_JPEG3 = 35
TAG_LOSSLESS2 = 36
TAG_SYMBOL_CLASS = 76
TAG_BINARY_DATA = 87


class SwfError(ValueError):
    pass


@dataclass
class ParsedSwf:
    images: dict[int, Image.Image] = field(default_factory=dict)
    binaries: dict[int, bytes] = field(default_factory=dict)
    # One image can be exported under several names when frames share a bitmap.
    symbols: dict[int, list[str]] = field(default_factory=dict)

    def named_images(self) -> dict[str, Image.Image]:
        return {name: image for key, image in self.images.items() for name in self.symbols.get(key, [])}

    def named_xml(self) -> dict[str, ET.Element]:
        result: dict[str, ET.Element] = {}
        for key, data in self.binaries.items():
            for name in self.symbols.get(key, []):
                result[name] = safe_fromstring(data)
        return result


def _inflate(data: bytes) -> bytes:
    decompressor = zlib.decompressobj()
    result = decompressor.decompress(data, MAX_SWF_BYTES)
    if decompressor.unconsumed_tail:
        raise SwfError("Decompressed data is too large.")
    return result


def _unpremultiply(r: int, g: int, b: int, a: int) -> bytes:
    if a in (0, 255):
        return bytes((r, g, b, a))
    return bytes((min(255, r * 255 // a), min(255, g * 255 // a), min(255, b * 255 // a), a))


def _decode_lossless(body: bytes, alpha: bool) -> tuple[int, Image.Image]:
    key, kind, width, height = struct.unpack_from("<HBHH", body)
    if not 0 < width * height <= MAX_IMAGE_PIXELS:
        raise SwfError("Bad image size.")
    pos = 7
    table_size = 0
    if kind == 3:
        table_size = body[pos] + 1
        pos += 1
    raw = _inflate(body[pos:])
    rgba = bytearray(width * height * 4)

    if kind == 3:
        entry = 4 if alpha else 3
        palette = raw[: table_size * entry]
        pixels = raw[table_size * entry :]
        stride = (width + 3) & ~3
        if len(pixels) < stride * height or len(palette) < table_size * entry:
            raise SwfError("Short image data.")
        for y in range(height):
            for x in range(width):
                index = pixels[y * stride + x]
                if index < table_size:
                    offset = index * entry
                    a = palette[offset + 3] if alpha else 255
                    target = (y * width + x) * 4
                    rgba[target : target + 4] = _unpremultiply(
                        palette[offset], palette[offset + 1], palette[offset + 2], a
                    )
    elif kind == 5:
        if len(raw) < width * height * 4:
            raise SwfError("Short image data.")
        for i in range(width * height):
            a, r, g, b = raw[i * 4 : i * 4 + 4]
            rgba[i * 4 : i * 4 + 4] = _unpremultiply(r, g, b, a if alpha else 255)
    else:
        raise SwfError(f"Unsupported image format {kind}.")
    return key, Image.frombytes("RGBA", (width, height), bytes(rgba))


def _decode_jpeg(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    if image.width * image.height > MAX_IMAGE_PIXELS:  # Checked before the pixels are decoded.
        raise SwfError("Bad image size.")
    return image.convert("RGBA")


def parse(data: bytes) -> ParsedSwf:
    try:
        return _parse(data)
    except SwfError:
        raise
    except (struct.error, IndexError, ValueError, OSError, UnidentifiedImageError, zlib.error) as exc:
        raise SwfError("The furni file is damaged.") from exc


def _parse(data: bytes) -> ParsedSwf:
    if not 8 <= len(data) <= MAX_SWF_BYTES:
        raise SwfError("Bad file size.")
    signature = data[:3]
    if signature == b"CWS":
        body = _inflate(data[8:])
    elif signature == b"FWS":
        body = data[8:]
    else:
        raise SwfError("Not a supported SWF file.")

    rect_bits = body[0] >> 3
    pos = (5 + rect_bits * 4 + 7) // 8 + 4
    swf = ParsedSwf()
    total_pixels = 0
    while pos + 2 <= len(body):
        code_and_length = struct.unpack_from("<H", body, pos)[0]
        pos += 2
        code, length = code_and_length >> 6, code_and_length & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", body, pos)[0]
            pos += 4
        if pos + length > len(body):
            raise SwfError("A tag runs past the end of the file.")
        tag = body[pos : pos + length]
        pos += length

        if code == TAG_END:
            break
        image: Image.Image | None = None
        if code in (TAG_LOSSLESS, TAG_LOSSLESS2):
            key, image = _decode_lossless(tag, alpha=code == TAG_LOSSLESS2)
        elif code == TAG_JPEG2:
            key, image = struct.unpack_from("<H", tag)[0], _decode_jpeg(tag[2:])
        elif code == TAG_JPEG3:
            end = 6 + struct.unpack_from("<I", tag, 2)[0]
            key, image = struct.unpack_from("<H", tag)[0], _decode_jpeg(tag[6:end])
        elif code == TAG_BINARY_DATA:
            swf.binaries[struct.unpack_from("<H", tag)[0]] = tag[6:]
        elif code == TAG_SYMBOL_CLASS:
            count = struct.unpack_from("<H", tag)[0]
            cursor = 2
            for _ in range(count):
                key = struct.unpack_from("<H", tag, cursor)[0]
                end = tag.index(b"\0", cursor + 2)
                swf.symbols.setdefault(key, []).append(tag[cursor + 2 : end].decode("utf-8", "replace"))
                cursor = end + 1
        if image is not None:
            total_pixels += image.width * image.height
            if total_pixels > MAX_TOTAL_PIXELS:
                raise SwfError("The file holds too many images.")
            swf.images[key] = image
    return swf


def _find_xml(xml: dict[str, ET.Element], suffix: str) -> ET.Element:
    for name, root in xml.items():
        if name.endswith(suffix):
            return root
    raise SwfError(f"The file has no {suffix} data.")


def _int(element: ET.Element | None, name: str, default: int = 0) -> int:
    value = element.get(name) if element is not None else None
    return int(value) if value else default


def _colors(visualization: ET.Element) -> dict[str, dict[str, str]]:
    colors: dict[str, dict[str, str]] = {}
    for color in visualization.findall("./colors/color"):
        layers = {layer.get("id", ""): layer.get("color", "") for layer in color.findall("colorLayer")}
        colors[color.get("id", "")] = {
            key: value for key, value in layers.items() if re.fullmatch(r"[0-9a-fA-F]{6}", value)
        }
    return colors


class _Atlas:
    """Packs images into rows. Identical images are stored once."""

    def __init__(self) -> None:
        self.placed: dict[int, tuple[int, int]] = {}
        self.images: list[tuple[Image.Image, int, int]] = []
        self.x = self.y = self.row = 0

    def add(self, image: Image.Image) -> tuple[int, int]:
        key = id(image)
        if key in self.placed:
            return self.placed[key]
        if image.width > ATLAS_WIDTH:
            raise SwfError("An image is too wide.")
        if self.x + image.width > ATLAS_WIDTH:
            self.x, self.y, self.row = 0, self.y + self.row + 1, 0
        if self.y + image.height > MAX_ATLAS_HEIGHT:
            raise SwfError("The furni has too many images.")
        spot = (self.x, self.y)
        self.images.append((image, *spot))
        self.placed[key] = spot
        self.x += image.width + 1
        self.row = max(self.row, image.height)
        return spot

    def render(self) -> bytes:
        canvas = Image.new("RGBA", (ATLAS_WIDTH, max(1, self.y + self.row)), (0, 0, 0, 0))
        for image, x, y in self.images:
            canvas.paste(image, (x, y))
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()


# Raised when the shape of a manifest changes, so art built before is built again.
ART_VERSION = 3
MAX_TRACK_FRAMES = 1000
DIGITS = 10


def _track_frames(layer: ET.Element) -> list[int]:
    """A layer's frames in playing order. Each sequence plays its own number of times."""
    frames: list[int] = []
    for sequence in layer.findall("frameSequence"):
        ids = [_int(frame, "id") for frame in sequence.findall("frame")]
        for _ in range(max(1, _int(sequence, "loopCount", 1))):
            frames += ids
            if len(frames) > MAX_TRACK_FRAMES:
                return frames[:MAX_TRACK_FRAMES]
    return frames


def build(data: bytes, classname: str) -> tuple[dict[str, Any], bytes]:
    """Returns the manifest and atlas PNG for one furni. Raises SwfError if it cannot be read."""
    try:
        parsed = parse(data)
        base = classname.split("*")[0]
        try:
            return _build(parsed, base)
        except SwfError:  # Too many frames to pack. A furni that stands still still beats no furni.
            return _build(parsed, base, animate=False)
    except SwfError:
        raise
    except (
        ValueError,
        KeyError,
        AttributeError,
        TypeError,
        ET.ParseError,
    ) as exc:  # Includes defusedxml's refusals.
        raise SwfError("The furni file is damaged.") from exc


def _layer_tracks(animation: ET.Element, direction: int, sprite_for: Any) -> list[dict[str, Any]]:
    """The layers of one state that change over time, each with its own sprites and speed."""
    tracks: list[dict[str, Any]] = []
    for layer_element in animation.findall("animationLayer"):
        frames = _track_frames(layer_element)
        if len(set(frames)) < 2:
            continue
        layer = _int(layer_element, "id")
        sprites = {frame: sprite_for(direction, layer, frame) for frame in set(frames)}
        loops = _int(layer_element, "loopCount", 1)
        tracks.append(
            {
                "layer": layer,
                "repeat": max(1, _int(layer_element, "frameRepeat", 1)),
                "loop": loops == 0,
                "frames": [sprites[frame] for frame in frames * max(1, min(loops, 10))],
            }
        )
    return tracks


def _digit_layers(direction: int, layer_count: int, sprite_for: Any) -> list[dict[str, dict[str, Any]]]:
    """Layers holding the digits 0 to 9, from the left of the display to the right."""
    found = []
    for layer in range(layer_count):
        sprites = {digit: sprite_for(direction, layer, digit) for digit in range(DIGITS)}
        if all(sprites.values()) and sprite_for(direction, layer, DIGITS) is None:
            found.append({str(digit): item for digit, item in sprites.items()})
    return sorted(found, key=lambda item: item["0"]["dx"])


def _build(swf: ParsedSwf, base: str, animate: bool = True) -> tuple[dict[str, Any], bytes]:
    images = swf.named_images()
    xml = swf.named_xml()
    assets = {a.get("name", ""): a for a in _find_xml(xml, "_assets").iter("asset")}
    visualization = next(
        (v for v in _find_xml(xml, "_visualization").iter("visualization") if v.get("size") == str(SIZE)),
        None,
    )
    if visualization is None:
        raise SwfError("The file has no 64 pixel images.")

    layer_config = {_int(e, "id"): e for e in visualization.findall("./layers/layer")}
    direction_config = {_int(e, "id"): e for e in visualization.findall("./directions/direction")}
    animations = {_int(e, "id"): e for e in visualization.findall("./animations/animation")}
    name_pattern = re.compile(rf"^{re.escape(base)}_{SIZE}_[a-z]_(\d)_\d+$")
    directions = sorted({int(m.group(1)) for name in assets if (m := name_pattern.match(name))})
    if not directions:
        raise SwfError("The file has no usable images.")
    # A transition plays on the way into a state, and is not a state you can choose.
    entering = {key: _int(a, "transitionTo") for key, a in animations.items() if a.get("transitionTo")}
    states = sorted({0} | {key for key in animations if key < 1000 and key not in entering})
    layer_count = _int(visualization, "layerCount", 1)
    if not 0 < layer_count <= 26:
        raise SwfError("Bad layer count.")

    atlas = _Atlas()
    poses: dict[str, list[dict[str, Any]]] = {}
    tracks: dict[str, list[dict[str, Any]]] = {}
    transitions: dict[str, list[dict[str, Any]]] = {}
    digits: dict[str, list[dict[str, dict[str, Any]]]] = {}

    def sprite(asset: ET.Element, layer: int, z: int, alpha: int, ink: str) -> dict[str, Any] | None:
        source = asset.get("source") or asset.get("name") or ""
        image = images.get(f"{base}_{source}") or images.get(source)
        if image is None:
            return None
        x, y = atlas.add(image)
        flip = asset.get("flipH") == "1"
        offset_x, offset_y = _int(asset, "x"), _int(asset, "y")
        return {
            "x": x,
            "y": y,
            "w": image.width,
            "h": image.height,
            # Offsets are measured from the tile centre, and from the mirrored edge when flipped.
            "dx": offset_x - image.width if flip else -offset_x,
            "dy": -offset_y,
            "flip": flip,
            "layer": layer,
            "z": z,
            "alpha": alpha,
            "ink": ink.lower(),
        }

    def sprite_for(direction: int, layer: int, frame: int) -> dict[str, Any] | None:
        asset = assets.get(f"{base}_{SIZE}_{chr(97 + layer)}_{direction}_{frame}")
        if asset is None:
            return None
        chosen = {
            _int(e, "id"): e
            for e in (direction_config[direction].findall("layer") if direction in direction_config else [])
        }
        config = layer_config.get(layer)
        z = _int(chosen.get(layer), "z", _int(config, "z"))
        ink = config.get("ink", "") if config is not None else ""
        return sprite(asset, layer, z, _int(config, "alpha", 255), ink)

    for direction in directions:
        layers_for_direction = {
            _int(e, "id"): e
            for e in (direction_config[direction].findall("layer") if direction in direction_config else [])
        }
        for state in states:
            frames: dict[int, int] = {}
            if state in animations:
                for animation_layer in animations[state].findall("animationLayer"):
                    frame = animation_layer.find("./frameSequence/frame")
                    if frame is not None:
                        frames[_int(animation_layer, "id")] = _int(frame, "id")
            sprites: list[dict[str, Any]] = []
            shadow = assets.get(f"{base}_{SIZE}_sd_{direction}_0")
            if shadow is not None and (s := sprite(shadow, -1, BELOW_EVERYTHING, SHADOW_ALPHA, "")):
                sprites.append(s)
            for layer in range(layer_count):
                asset = assets.get(f"{base}_{SIZE}_{chr(97 + layer)}_{direction}_{frames.get(layer, 0)}")
                if asset is None:
                    continue
                config = layer_config.get(layer)
                z = _int(layers_for_direction.get(layer), "z", _int(config, "z"))
                alpha = _int(config, "alpha", 255)
                ink = config.get("ink", "") if config is not None else ""
                if s := sprite(asset, layer, z, alpha, ink):
                    sprites.append(s)
            sprites.sort(key=lambda item: item["z"])
            poses[f"{direction}:{state}"] = sprites
            if animate and state in animations:
                moving = _layer_tracks(animations[state], direction, sprite_for)
                if moving:
                    tracks[f"{direction}:{state}"] = moving
        for key, into in entering.items():
            if animate and (moving := _layer_tracks(animations[key], direction, sprite_for)):
                transitions.setdefault(f"{direction}:{into}", moving)
        if animate and (found := _digit_layers(direction, layer_count, sprite_for)):
            digits[str(direction)] = found

    manifest = {
        "size": SIZE,
        "directions": directions,
        "states": states,
        "colors": _colors(visualization),
        "poses": poses,
        "tracks": tracks,
        "transitions": transitions,
        "digits": digits,
    }
    return manifest, atlas.render()
