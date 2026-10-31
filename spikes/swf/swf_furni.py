"""Spike: read a Habbo furni SWF with no Flash tooling.

Parses only the tags furni use: images, binary XML data and symbol names. Treats the file as
untrusted input, so every read is bounds-checked and decompression is size-limited.
"""

from __future__ import annotations

import io
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field

from defusedxml.ElementTree import fromstring as defused_fromstring
from PIL import Image

MAX_SWF_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 4096 * 4096

TAG_SYMBOL_CLASS = 76
TAG_BINARY_DATA = 87
TAG_LOSSLESS = 20
TAG_LOSSLESS2 = 36
TAG_JPEG2 = 21
TAG_JPEG3 = 35


class SwfError(ValueError):
    pass


@dataclass
class FurniSwf:
    images: dict[int, Image.Image] = field(default_factory=dict)
    binaries: dict[int, bytes] = field(default_factory=dict)
    # One character can be exported under several names when frames share a bitmap.
    symbols: dict[int, list[str]] = field(default_factory=dict)
    unsupported_tags: dict[int, int] = field(default_factory=dict)

    def named_images(self) -> dict[str, Image.Image]:
        return {name: img for i, img in self.images.items() for name in self.symbols.get(i, [])}

    def named_xml(self) -> dict[str, ET.Element]:
        out = {}
        for char_id, data in self.binaries.items():
            for name in self.symbols.get(char_id, []):
                out[name] = defused_fromstring(data)
        return out


def _inflate(data: bytes) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(data, MAX_SWF_BYTES)
    if d.unconsumed_tail:
        raise SwfError("decompressed data too large")
    return out


def _skip_rect(buf: bytes, pos: int) -> int:
    bits = buf[pos] >> 3
    return pos + (5 + bits * 4 + 7) // 8


def _decode_lossless(body: bytes, alpha: bool) -> tuple[int, Image.Image]:
    char_id, fmt, width, height = struct.unpack_from("<HBHH", body)
    if width * height > MAX_IMAGE_PIXELS or width == 0 or height == 0:
        raise SwfError("bad image size")
    pos = 7
    table_size = 0
    if fmt == 3:
        table_size = body[pos] + 1
        pos += 1
    raw = _inflate(body[pos:])

    if fmt == 3:
        entry = 4 if alpha else 3
        palette = raw[: table_size * entry]
        pixels = raw[table_size * entry :]
        stride = (width + 3) & ~3
        rgba = bytearray(width * height * 4)
        for y in range(height):
            for x in range(width):
                index = pixels[y * stride + x]
                if index >= table_size:
                    continue
                offset = index * entry
                a = palette[offset + 3] if alpha else 255
                rgba[(y * width + x) * 4 : (y * width + x) * 4 + 4] = _unpremultiply(
                    palette[offset], palette[offset + 1], palette[offset + 2], a
                )
    elif fmt == 5:
        if len(raw) < width * height * 4:
            raise SwfError("short image data")
        rgba = bytearray(width * height * 4)
        for i in range(width * height):
            a, r, g, b = raw[i * 4 : i * 4 + 4]
            if not alpha:
                a = 255
            rgba[i * 4 : i * 4 + 4] = _unpremultiply(r, g, b, a)
    else:
        raise SwfError(f"unsupported lossless format {fmt}")
    return char_id, Image.frombytes("RGBA", (width, height), bytes(rgba))


def _unpremultiply(r: int, g: int, b: int, a: int) -> bytes:
    if a in (0, 255):
        return bytes((r, g, b, a))
    return bytes((min(255, r * 255 // a), min(255, g * 255 // a), min(255, b * 255 // a), a))


def parse(data: bytes) -> FurniSwf:
    if len(data) < 8 or len(data) > MAX_SWF_BYTES:
        raise SwfError("bad file size")
    signature = data[:3]
    if signature == b"CWS":
        body = _inflate(data[8:])
    elif signature == b"FWS":
        body = data[8:]
    else:
        raise SwfError(f"unsupported signature {signature!r}")

    pos = _skip_rect(body, 0) + 4
    swf = FurniSwf()
    while pos + 2 <= len(body):
        code_len = struct.unpack_from("<H", body, pos)[0]
        pos += 2
        code, length = code_len >> 6, code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", body, pos)[0]
            pos += 4
        if pos + length > len(body):
            raise SwfError("tag overruns file")
        tag = body[pos : pos + length]
        pos += length

        if code == 0:
            break
        if code == TAG_LOSSLESS or code == TAG_LOSSLESS2:
            char_id, image = _decode_lossless(tag, alpha=code == TAG_LOSSLESS2)
            swf.images[char_id] = image
        elif code == TAG_BINARY_DATA:
            swf.binaries[struct.unpack_from("<H", tag)[0]] = tag[6:]
        elif code == TAG_SYMBOL_CLASS:
            count = struct.unpack_from("<H", tag)[0]
            p = 2
            for _ in range(count):
                char_id = struct.unpack_from("<H", tag, p)[0]
                end = tag.index(b"\0", p + 2)
                swf.symbols.setdefault(char_id, []).append(tag[p + 2 : end].decode("utf-8", "replace"))
                p = end + 1
        elif code in (TAG_JPEG2, TAG_JPEG3):
            char_id = struct.unpack_from("<H", tag)[0]
            jpeg_end = 2 + struct.unpack_from("<I", tag, 2)[0] + 4 if code == TAG_JPEG3 else len(tag)
            start = 6 if code == TAG_JPEG3 else 2
            swf.images[char_id] = Image.open(io.BytesIO(tag[start:jpeg_end])).convert("RGBA")
        elif code not in (1, 9, 41, 43, 65, 69, 77, 82, 86):
            swf.unsupported_tags[code] = swf.unsupported_tags.get(code, 0) + 1
    return swf


@dataclass
class Sprite:
    image: Image.Image
    x: int
    y: int
    flip: bool
    layer: str
    z: int
    alpha: int
    ink: str


def _find_xml(xml: dict[str, ET.Element], suffix: str) -> ET.Element:
    for name, root in xml.items():
        if name.endswith(suffix):
            return root
    raise SwfError(f"no {suffix} xml")


def compose(swf: FurniSwf, classname: str, size: int = 64, direction: int = 2, state: int = 0) -> list[Sprite]:
    """Return the sprites to draw for one furni pose, back to front."""
    base = classname.split("*")[0]
    images = swf.named_images()
    xml = swf.named_xml()
    assets = {a.get("name"): a for a in _find_xml(xml, "_assets").iter("asset")}
    vis_root = _find_xml(xml, "_visualization")
    vis = next((v for v in vis_root.iter("visualization") if v.get("size") == str(size)), None)
    if vis is None:
        raise SwfError(f"no visualization for size {size}")

    layer_count = int(vis.get("layerCount", "1"))
    layer_cfg = {int(l.get("id")): l for l in vis.findall("./layers/layer")}
    dir_cfg = next((d for d in vis.findall("./directions/direction") if d.get("id") == str(direction)), None)
    dir_layers = {int(l.get("id")): l for l in dir_cfg.findall("layer")} if dir_cfg is not None else {}
    anim = next((a for a in vis.findall("./animations/animation") if a.get("id") == str(state)), None)

    frames = {}
    if anim is not None:
        for anim_layer in anim.findall("animationLayer"):
            frame = anim_layer.find("./frameSequence/frame")
            if frame is not None:
                frames[int(anim_layer.get("id"))] = int(frame.get("id", "0"))

    sprites = []
    shadow = assets.get(f"{base}_{size}_sd_{direction}_0")
    if shadow is not None:
        source = shadow.get("source") or shadow.get("name")
        image = images.get(f"{base}_{source}") or images.get(source)
        if image is not None:
            sprites.append(
                Sprite(image, int(shadow.get("x", "0")), int(shadow.get("y", "0")), shadow.get("flipH") == "1", "sd", -9999, 48, "")
            )
    for i in range(layer_count):
        letter = chr(ord("a") + i)
        name = f"{base}_{size}_{letter}_{direction}_{frames.get(i, 0)}"
        asset = assets.get(name)
        if asset is None:
            continue
        source = asset.get("source") or name
        image = images.get(f"{base}_{source}") or images.get(source)
        if image is None:
            continue
        cfg = layer_cfg.get(i)
        dcfg = dir_layers.get(i)
        z = int(cfg.get("z", "0")) if cfg is not None else 0
        if dcfg is not None and dcfg.get("z"):
            z = int(dcfg.get("z"))
        sprites.append(
            Sprite(
                image=image,
                x=int(asset.get("x", "0")),
                y=int(asset.get("y", "0")),
                flip=asset.get("flipH") == "1",
                layer=letter,
                z=z,
                alpha=int(cfg.get("alpha", "255")) if cfg is not None else 255,
                ink=cfg.get("ink", "") if cfg is not None else "",
            )
        )
    sprites.sort(key=lambda s: s.z)
    return sprites


def render(sprites: list[Sprite], canvas: int = 256) -> Image.Image:
    """Draw sprites around the tile origin. Offsets are `x`/`y` subtracted from the origin."""
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    ox, oy = canvas // 2, canvas * 2 // 3
    for s in sprites:
        image = s.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if s.flip else s.image
        if s.alpha != 255:
            image = image.copy()
            image.putalpha(image.getchannel("A").point(lambda v: v * s.alpha // 255))
        # flipH offsets are measured from the mirrored edge.
        x = ox + s.x - image.width if s.flip else ox - s.x
        y = oy - s.y
        if s.ink.upper() == "ADD":
            base = out.crop((x, y, x + image.width, y + image.height)).convert("RGBA")
            image = _add_blend(base, image)
        out.alpha_composite(image, dest=(max(0, x), max(0, y)))
    return out


def _add_blend(base: Image.Image, top: Image.Image) -> Image.Image:
    from PIL import ImageChops

    a = top.getchannel("A")
    rgb = ImageChops.add(base.convert("RGB"), Image.composite(top.convert("RGB"), Image.new("RGB", top.size), a))
    out = rgb.convert("RGBA")
    out.putalpha(ImageChops.lighter(base.getchannel("A"), a))
    return out


def asset_names(xml_root: ET.Element) -> list[str]:
    return [a.get("name") for a in xml_root.iter("asset") if a.get("name")]


def directions_of(swf: FurniSwf, classname: str, size: int = 64) -> list[int]:
    base = classname.split("*")[0]
    assets = _find_xml(swf.named_xml(), "_assets")
    pattern = re.compile(rf"^{re.escape(base)}_{size}_[a-z]_(\d)_\d+$")
    return sorted({int(m.group(1)) for n in asset_names(assets) if (m := pattern.match(n))})
