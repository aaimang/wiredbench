"""Builds small real SWF files for tests, so no Habbo files are stored in the repo."""

from __future__ import annotations

import struct
import zlib


def _tag(code: int, body: bytes) -> bytes:
    return struct.pack("<HI", (code << 6) | 0x3F, len(body)) + body


def _image(key: int, width: int, height: int, argb: bytes) -> bytes:
    return _tag(36, struct.pack("<HBHH", key, 5, width, height) + zlib.compress(argb * (width * height)))


def _binary(key: int, text: str) -> bytes:
    return _tag(87, struct.pack("<HI", key, 0) + text.encode())


def _symbols(names: dict[int, list[str]]) -> bytes:
    pairs = [(key, name) for key, group in names.items() for name in group]
    body = struct.pack("<H", len(pairs)) + b"".join(
        struct.pack("<H", k) + n.encode() + b"\0" for k, n in pairs
    )
    return _tag(76, body)


def wrap(tags: bytes, compressed: bool = True) -> bytes:
    body = b"\x00" + b"\x00\x00\x00\x00" + tags + b"\x00\x00"
    if compressed:
        return b"CWS\x0a" + struct.pack("<I", len(body) + 8) + zlib.compress(body)
    return b"FWS\x0a" + struct.pack("<I", len(body) + 8) + body


def furni_swf(base: str, width: int = 40, height: int = 50, compressed: bool = True) -> bytes:
    """One furni: directions 2 and 4 (4 is a mirrored copy), two states, a shadow and a tinted layer."""
    assets = f"""<assets>
      <asset name="{base}_64_a_2_0" x="20" y="40"/>
      <asset name="{base}_64_a_2_1" x="20" y="40"/>
      <asset name="{base}_64_a_4_0" source="{base}_64_a_2_0" x="30" y="40" flipH="1"/>
      <asset name="{base}_64_a_4_1" source="{base}_64_a_2_1" x="30" y="40" flipH="1"/>
      <asset name="{base}_64_b_2_0" x="5" y="10"/>
      <asset name="{base}_64_b_4_0" source="{base}_64_b_2_0" x="5" y="10"/>
      <asset name="{base}_64_sd_2_0" x="10" y="0"/>
    </assets>"""
    visualization = f"""<visualizationData type="{base}">
      <graphics><visualization size="64" layerCount="2" angle="45">
        <layers><layer id="1" z="5" alpha="128" ink="ADD"/></layers>
        <directions><direction id="4"><layer id="1" z="-3"/></direction></directions>
        <colors><color id="1"><colorLayer id="0" color="ff1f08"/></color></colors>
        <animations>
          <animation id="0"><animationLayer id="0"><frameSequence><frame id="0"/></frameSequence></animationLayer></animation>
          <animation id="1"><animationLayer id="0"><frameSequence><frame id="1"/></frameSequence></animationLayer></animation>
          <animation id="1000"><animationLayer id="0"><frameSequence><frame id="1"/></frameSequence></animationLayer></animation>
        </animations>
      </visualization></graphics></visualizationData>"""
    tags = (
        _image(1, width, height, b"\xff\xc8\x32\x1e")
        + _image(2, width, height, b"\xff\x2b\x7a\x3d")
        + _image(3, 10, 10, b"\x80\x40\x40\x40")
        + _image(4, 8, 6, b"\xff\x00\x00\x00")
        + _binary(10, assets)
        + _binary(11, visualization)
        + _symbols(
            {
                1: [f"{base}_{base}_64_a_2_0"],
                2: [f"{base}_{base}_64_a_2_1"],
                3: [f"{base}_{base}_64_b_2_0"],
                4: [f"{base}_{base}_64_sd_2_0"],
                10: [f"{base}_{base}_assets"],
                11: [f"{base}_{base}_visualization"],
            }
        )
    )
    return wrap(tags, compressed)
