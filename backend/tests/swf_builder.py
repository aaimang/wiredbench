"""Builds small real SWF files for tests, so no Habbo files are stored in the repo."""

from __future__ import annotations

import re
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


def furni_swf(
    base: str, width: int = 40, height: int = 50, compressed: bool = True, logic: str | None = None
) -> bytes:
    """One furni: directions 2 and 4 (4 is a mirrored copy), two states, a shadow and a tinted layer.

    With `logic`, it also has an index naming that logic and a one-tile model.
    """
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
    if logic:
        tags += (
            _binary(12, f'<object type="{base}" visualization="furniture_animated" logic="{logic}"/>')
            + _binary(
                13, f'<objectData type="{base}"><model><dimensions x="1" y="1" z="1.0"/></model></objectData>'
            )
            + _symbols({12: [f"{base}_index"], 13: [f"{base}_{base}_logic"]})
        )
    return wrap(tags, compressed)


def effect_swf(
    lib: str, animation: str, extra_aliases: str = "", shadow: str = "", offsets: bool = True
) -> bytes:
    """An effect library: one sprite drawn for direction 0, with frames 0 and 1.

    With a shadow name, the library also has that shadow as a black block without an offset.
    """
    shadow_asset = f'<asset name="h_{shadow}_0" mimeType="image/png"/>' if shadow else ""
    manifest = f"""<?xml version="1.0"?><manifest><library id="{lib}"><assets>
      <asset name="h_std_fx1_1_1_0_0" mimeType="image/png"><param key="offset" value="-10,80"/></asset>
      <asset name="h_std_fx1_1_1_0_1" mimeType="image/png"><param key="offset" value="-12,70"/></asset>
      {shadow_asset}
    </assets><aliases>
      <alias name="h_std_fx1_1_1_2_0" link="h_std_fx1_1_1_0_0" fliph="0" flipv="0"/>
      <alias name="h_std_fx1_1_1_4_0" link="h_std_fx1_1_1_0_0" fliph="1" flipv="0"/>
      {extra_aliases}
    </aliases></library></manifest>"""
    if not offsets:  # Older effects such as Wade list their images without an offset.
        manifest = re.sub(r'><param key="offset" value="[^"]*"/></asset>', "/>", manifest)
    tags = (
        _image(1, 4, 6, b"\xff\xff\xff\x00")
        + _image(2, 5, 7, b"\xff\x00\xff\xff")
        + _binary(3, manifest)
        + _binary(4, animation)
        + (_image(5, 6, 3, b"\xff\x00\x00\x00") if shadow else b"")
        + _symbols(
            {
                1: [f"{lib}_h_std_fx1_1_1_0_0"],
                2: [f"{lib}_h_std_fx1_1_1_0_1"],
                3: [f"{lib}_manifest"],
                4: [f"{lib}_animation"],
                **({5: [f"{lib}_h_{shadow}_0"]} if shadow else {}),
            }
        )
    )
    return wrap(tags)


def figure_library(lib: str, assets: dict[str, tuple[int, int, bytes, tuple[int, int]]]) -> bytes:
    """A figure part library: each asset is a solid block of one ARGB colour at a manifest offset."""
    rows = "".join(
        f'<asset name="{name}" mimeType="image/png"><param key="offset" value="{ox},{oy}"/></asset>'
        for name, (_, _, _, (ox, oy)) in assets.items()
    )
    manifest = (
        f'<?xml version="1.0"?><manifest><library id="{lib}"><assets>{rows}</assets></library></manifest>'
    )
    tags = b"".join(_image(key, w, h, argb) for key, (w, h, argb, _) in enumerate(assets.values(), 1))
    symbols = {key: [f"{lib}_{name}"] for key, name in enumerate(assets, 1)}
    manifest_key = len(assets) + 1
    symbols[manifest_key] = [f"{lib}_manifest"]
    return wrap(tags + _binary(manifest_key, manifest) + _symbols(symbols))
