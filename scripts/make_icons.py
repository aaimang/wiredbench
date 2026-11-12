"""Draws Wiredbench's icons (turbo-plugin/wwwroot/*.png) and logo (docs/wiredbench-logo.svg).

Pixel art, as the Habbo client's own icons are, in the look of Habbo's WIRED banners: a chunky cyan
W with a darker edge and a dark outline, standing on a dark WIRED box rimmed in white. Each tool's
icon is its sign, big at the front, with the WIRED box of its kind behind: a gold magnifier on the
brown trigger box (trace), a green cube on the grey effect box (sandbox), a disk on the white
condition box (presets), a warning sign on the add-on box (check) and a check mark (parity).

The toolbar gets the mark at the size of its icon slot (toolbar.png, 44 x 40); windows and the
panel take it square (wiredbench.png, 32 x 32). The SVG is the toolbar mark, a square per pixel.

    uv run --no-project --with pillow python scripts/make_icons.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "turbo-plugin" / "wwwroot"
LOGO = ROOT / "docs" / "wiredbench-logo.svg"

Colour = tuple[int, int, int, int]
Pixels = set[tuple[int, int]]

OUTLINE: Colour = (12, 28, 44, 255)
RIM: Colour = (214, 228, 236, 255)
CYAN: Colour = (78, 214, 232, 255)
CYAN_LIGHT: Colour = (170, 244, 250, 255)
CYAN_SIDE: Colour = (28, 140, 160, 255)
CYAN_DEEP: Colour = (18, 100, 118, 255)
WHITE: Colour = (255, 255, 255, 255)
CLEAR: Colour = (0, 0, 0, 0)

# The W of the WIRED banners on a block grid: outer stems, a peak in the middle, solid below.
W_GRID = [
    "XXX.....XXX",
    "XXX.....XXX",
    "XXX.....XXX",
    "XXX..X..XXX",
    "XXX.XXX.XXX",
    "XXXXXXXXXXX",
    ".XXXX.XXXX.",
]

# WIRED boxes as the banners colour them: top, top highlight, left side, right side.
BOXES: dict[str, tuple[Colour, Colour, Colour, Colour]] = {
    "trigger": ((112, 74, 50, 255), (140, 98, 70, 255), (74, 46, 30, 255), (92, 58, 38, 255)),
    "effect": ((206, 204, 196, 255), (232, 230, 224, 255), (128, 126, 120, 255), (160, 158, 150, 255)),
    "condition": ((244, 244, 240, 255), (255, 255, 255, 255), (176, 178, 176, 255), (206, 208, 206, 255)),
    "addon": ((150, 150, 146, 255), (180, 180, 176, 255), (86, 86, 84, 255), (110, 110, 106, 255)),
    "dark": ((40, 46, 52, 255), (62, 70, 78, 255), (20, 24, 28, 255), (30, 34, 40, 255)),
    "green": ((132, 222, 92, 255), (178, 240, 140, 255), (64, 150, 46, 255), (88, 182, 62, 255)),
}

PALETTE: dict[str, Colour] = {
    "Y": (250, 200, 40, 255),
    "y": (255, 236, 140, 255),
    "u": (196, 140, 20, 255),
    "c": (150, 226, 240, 255),
    "w": WHITE,
    "b": (120, 74, 40, 255),
    "B": (86, 50, 26, 255),
    "P": (150, 90, 210, 255),
    "p": (110, 60, 160, 255),
    "m": (190, 200, 210, 255),
    "k": (24, 28, 34, 255),
    "C": CYAN,
    "g": (120, 214, 80, 255),
    "d": (52, 130, 40, 255),
}

# Each tool's sign, one letter of PALETTE per pixel; an outline is drawn around it. The sandbox's
# sign is a small green box (sign()).
SIGNS: dict[str, list[str]] = {
    "trace": [
        "...YYYYY......",
        "..YyyyyyY.....",
        ".YyccccccY....",
        "YyccwwccccY...",
        "YycwccccccY...",
        "YccwcccccuY...",
        "YccccccccuY...",
        "YcccccccuuY...",
        ".YccccuuuY....",
        "..YuuuuuYbb...",
        "...YYYYYbbbB..",
        "........bbbbB.",
        ".........bbbbB",
        "..........bbB.",
    ],
    "presets": [
        "PPPPPPPPPPPPP.",
        "PpmmmmmmmkmpPP",
        "PpmmmmmmmkmpPP",
        "PpmmmmmmmmmpPP",
        "PppppppppppppP",
        "PwwwwwwwwwwwwP",
        "PwwwCCCCCwwwwP",
        "PwwCwwwwwwwwwP",
        "PwwCwwwCCCwwwP",
        "PwwCwwwwwCwwwP",
        "PwwwCCCCCwwwwP",
        "PwwwwwwwwwwwwP",
        "PPPPPPPPPPPPPP",
    ],
    "check": [
        "......Y......",
        ".....YyY.....",
        ".....YyY.....",
        "....YykyY....",
        "....YykyY....",
        "...YyykyyY...",
        "...YyykyyY...",
        "..YyyykyyyY..",
        "..YyyyyyyyY..",
        ".YyyyykyyyyY.",
        ".YyyyyyyyyyY.",
        "YuuuuuuuuuuuY",
        "YYYYYYYYYYYYY",
    ],
    "parity": [
        "...........ggg",
        "..........gggd",
        ".........gggd.",
        "gg......gggd..",
        "ggg....gggd...",
        "dggg..gggd....",
        ".dggggggd.....",
        "..dggggd......",
        "...dggd.......",
        "....dd........",
    ],
}

# Each tool's box, and the colour of the light on its side.
TOOLS: dict[str, tuple[str, Colour]] = {
    "trace": ("trigger", PALETTE["Y"]),
    "sandbox": ("effect", PALETTE["g"]),
    "presets": ("condition", PALETTE["P"]),
    "check": ("addon", (230, 70, 50, 255)),
    "parity": ("effect", PALETTE["g"]),
}


def _outlined(im: Image.Image, colour: Colour, diagonal: bool = False) -> Image.Image:
    """`im` one pixel larger each way, with a line of `colour` around what it holds."""
    out = Image.new("RGBA", (im.width + 2, im.height + 2), CLEAR)
    out.alpha_composite(im, (1, 1))
    px = out.load()
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)] + ([(1, 1), (-1, -1), (1, -1), (-1, 1)] if diagonal else [])
    body = {(x, y) for y in range(out.height) for x in range(out.width) if px[x, y][3]}
    for x, y in body:
        for dx, dy in steps:
            n = (x + dx, y + dy)
            if n not in body and 0 <= n[0] < out.width and 0 <= n[1] < out.height:
                px[n] = colour
    return out


def letter(block: int, depth: int) -> Image.Image:
    """The W: its face in cyan, lit along the top, extruded `depth` pixels down, outlined."""
    face: Pixels = {
        (x * block + i, y * block + j)
        for y, row in enumerate(W_GRID)
        for x, c in enumerate(row)
        if c == "X"
        for i in range(block)
        for j in range(block)
    }
    side = {(x, y + k) for x, y in face for k in range(1, depth + 1)} - face
    body = face | side
    im = Image.new("RGBA", (len(W_GRID[0]) * block, len(W_GRID) * block + depth), CLEAR)
    px = im.load()
    for x, y in side:
        px[x, y] = CYAN_DEEP if (x, y + 1) not in body else CYAN_SIDE
    for x, y in face:
        px[x, y] = CYAN_LIGHT if (x, y - 1) not in face else CYAN
    # A glint on the top left of each outer stem.
    for gx, gy in ((1, 1), (2, 1), (1, 2)):
        for stem in (0, 8 * block):
            if (stem + gx, gy) in face:
                px[stem + gx, gy] = WHITE
    return _outlined(im, OUTLINE, diagonal=True)


def box(kind: str, width: int, height: int, light: Colour | None = None) -> Image.Image:
    """An isometric WIRED box: a 2:1 diamond top `width` wide over sides `height` deep, outlined."""
    top, shine, left, right = BOXES[kind]
    hw, qh = width // 2, width // 4
    im = Image.new("RGBA", (width + 1, 2 * qh + height + 1), CLEAR)
    d = ImageDraw.Draw(im)
    d.polygon([(0, qh), (hw, 2 * qh), (hw, 2 * qh + height), (0, qh + height)], fill=left)
    d.polygon([(hw, 2 * qh), (width, qh), (width, qh + height), (hw, 2 * qh + height)], fill=right)
    d.polygon([(hw, 0), (width, qh), (hw, 2 * qh), (0, qh)], fill=top)
    d.polygon([(hw, 0), (width - 3, qh - 1), (hw, 2 * qh - 4), (3, qh - 1)], fill=shine)
    d.polygon([(hw, 3), (width - 6, qh - 1), (hw, 2 * qh - 6), (6, qh - 1)], fill=top)
    d.line([(0, qh), (hw, 2 * qh), (width, qh)], fill=OUTLINE)
    d.line([(hw, 2 * qh), (hw, 2 * qh + height)], fill=OUTLINE)
    if light is not None:
        lx, ly = hw + (width - hw) * 2 // 3, qh + height // 2 + 2
        d.rectangle((lx, ly, lx + 1, ly + 1), fill=light)
    return _outlined(im, OUTLINE)


def sign(name: str) -> Image.Image:
    if name == "sandbox":
        return box("green", 14, 7)
    rows = SIGNS[name]
    im = Image.new("RGBA", (len(rows[0]), len(rows)), CLEAR)
    px = im.load()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                px[x, y] = PALETTE[c]
    return _outlined(im, OUTLINE, diagonal=True)


def mark(size: tuple[int, int], box_width: int, box_height: int, block: int) -> Image.Image:
    """The W standing on a dark WIRED box rimmed in white, at the bottom middle of `size`."""
    icon = Image.new("RGBA", size, CLEAR)
    base = _outlined(box("dark", box_width, box_height), RIM)
    bx, by = (size[0] - base.width) // 2, size[1] - base.height
    icon.alpha_composite(base, (bx, by))
    w = letter(block, 2)
    wx, wy = (size[0] - w.width) // 2, by - w.height + base.height // 2
    # The rim belongs to the box's edge: none of it shows through the W's open top.
    px = icon.load()
    for y in range(max(0, wy), wy + w.height):
        for x in range(wx, wx + w.width):
            if px[x, y] == RIM:
                px[x, y] = CLEAR
    icon.alpha_composite(w, (wx, wy))
    return icon


def tool(name: str) -> Image.Image:
    """A tool's 32 x 32 icon: its sign big at the front left, its WIRED box behind on the right."""
    kind, light = TOOLS[name]
    icon = Image.new("RGBA", (32, 32), CLEAR)
    b = box(kind, 20, 6, light)
    icon.alpha_composite(b, (32 - b.width, 32 - b.height - 5))
    s = sign(name)
    icon.alpha_composite(s, (0, 32 - s.height))
    return icon


def svg(image: Image.Image) -> str:
    """The picture as an SVG of square pixels, a rectangle for each run of one colour in a row."""
    px = image.load()
    rects = []
    for y in range(image.height):
        x = 0
        while x < image.width:
            colour = px[x, y]
            run = 1
            while x + run < image.width and px[x + run, y] == colour:
                run += 1
            if colour[3]:
                fill = "#{:02x}{:02x}{:02x}".format(*colour[:3])
                rects.append(f'<rect x="{x}" y="{y}" width="{run}" height="1" fill="{fill}"/>')
            x += run
    body = "\n  ".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {image.width} {image.height}" '
        f'width="{image.width * 8}" height="{image.height * 8}" shape-rendering="crispEdges">\n'
        f"  <title>Wiredbench</title>\n  {body}\n</svg>\n"
    )


GLYPH = 14
GLYPH_SCALE = 8
GLYPH_WHITE = "#ffffff"


def _glyph(paint: Callable[[ImageDraw.ImageDraw, float], None]) -> Image.Image:
    """A small white sign for an icon button, drawn on a 14 x 14 grid and scaled down smooth."""
    k = GLYPH_SCALE
    image = Image.new("RGBA", (GLYPH * k, GLYPH * k), CLEAR)
    paint(ImageDraw.Draw(image), k)

    return image.resize((GLYPH, GLYPH), Image.Resampling.LANCZOS)


def glyph_delete(draw: ImageDraw.ImageDraw, k: float) -> None:
    """A bin: its lid, handle and body."""
    draw.rectangle((2 * k, 3 * k, 12 * k, 4.4 * k), fill=GLYPH_WHITE)
    draw.rectangle((5.5 * k, 1.5 * k, 8.5 * k, 3 * k), fill=GLYPH_WHITE)
    draw.polygon(
        [(3.2 * k, 5.2 * k), (10.8 * k, 5.2 * k), (10 * k, 12.6 * k), (4 * k, 12.6 * k)], fill=GLYPH_WHITE
    )


def glyph_refresh(draw: ImageDraw.ImageDraw, k: float) -> None:
    """A circling arrow."""
    draw.arc((2 * k, 2 * k, 12 * k, 12 * k), 40, 330, fill=GLYPH_WHITE, width=round(1.8 * k))
    draw.polygon([(12.6 * k, 1.2 * k), (12.6 * k, 6.4 * k), (7.6 * k, 4.6 * k)], fill=GLYPH_WHITE)


GLYPHS: dict[str, Callable[[ImageDraw.ImageDraw, float], None]] = {
    "icon-delete": glyph_delete,
    "icon-refresh": glyph_refresh,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pictures = {
        "toolbar": mark((44, 40), 38, 8, 2),
        "wiredbench": mark((32, 32), 28, 6, 2),
        **{name: tool(name) for name in TOOLS},
        **{name: _glyph(paint) for name, paint in GLYPHS.items()},
    }
    for name, picture in pictures.items():
        picture.save(OUT / f"{name}.png")
        print(f"wrote {OUT / f'{name}.png'}")

    LOGO.write_text(svg(pictures["toolbar"]), encoding="utf-8")
    print(f"wrote {LOGO}")


if __name__ == "__main__":
    main()
