"""Draws Wiredbench's client and panel icons (turbo-plugin/wwwroot/*.png) from the Wiredbench mark.

Every icon is the mark of frontend/public/favicon.svg: a dark isometric WIRED tile with a light top,
and a red sign on it saying what the window is for. Drawn at four times the size and scaled down, so
the edges are smooth at 32 x 32.

    uv run --with pillow python scripts/make_icons.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "turbo-plugin" / "wwwroot"
SIZE = 32
SCALE = 4
DARK = "#1c211c"
TOP = "#e4e5dc"
RED = "#c8321e"
WIDTH = 2.4


def _s(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(x * SCALE, y * SCALE) for x, y in points]


def _tile(draw: ImageDraw.ImageDraw) -> None:
    # favicon.svg: M16 5 30 12.5v7L16 27 2 19.5v-7z, and the top M16 7.8 25.8 13 16 18.2 6.2 13z.
    draw.polygon(_s([(16, 5), (30, 12.5), (30, 19.5), (16, 27), (2, 19.5), (2, 12.5)]), fill=DARK)
    draw.polygon(_s([(16, 7.8), (25.8, 13), (16, 18.2), (6.2, 13)]), fill=TOP)


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], width: float = WIDTH) -> None:
    draw.line(_s(points), fill=RED, width=round(width * SCALE), joint="curve")

    for x, y in _s([points[0], points[-1]]):
        r = width * SCALE / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=RED)


def pulse(draw: ImageDraw.ImageDraw) -> None:
    """The Wiredbench mark's own sign: a pulse across the tile."""
    _line(draw, [(10.5, 13), (15.5, 13), (17, 10.5), (18.5, 15.5), (19.8, 13), (22, 13)])


def trace(draw: ImageDraw.ImageDraw) -> None:
    """A magnifier over the pulse: following what a stack does."""
    _line(draw, [(9.5, 13), (12.5, 13), (13.5, 11.5), (14.5, 14.5), (15.3, 13)], 1.8)
    r = 2.6 * SCALE
    cx, cy = 18.5 * SCALE, 12.2 * SCALE
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RED, width=round(1.6 * SCALE))
    _line(draw, [(20.4, 14.1), (22.6, 16.2)], 2.0)


def sandbox(draw: ImageDraw.ImageDraw) -> None:
    """A small box standing on the tile: a room to build in and put back."""
    draw.polygon(_s([(16, 9.4), (20.6, 11.8), (16, 14.2), (11.4, 11.8)]), fill=RED)
    draw.polygon(_s([(11.4, 11.8), (16, 14.2), (16, 16.6), (11.4, 14.2)]), fill="#8e2214")
    draw.polygon(_s([(16, 14.2), (20.6, 11.8), (20.6, 14.2), (16, 16.6)]), fill="#a92a18")


def presets(draw: ImageDraw.ImageDraw) -> None:
    """A G on the tile: G-Presets files."""
    w = round(1.5 * SCALE)
    box = (11.6 * SCALE, 9.6 * SCALE, 20.4 * SCALE, 16.4 * SCALE)
    draw.arc(box, 40, 330, fill=RED, width=w)
    draw.line(_s([(16.4, 13.2), (20.2, 13.2)]), fill=RED, width=w)
    draw.line(_s([(19.6, 13.2), (19.6, 15.2)]), fill=RED, width=w)


def parity(draw: ImageDraw.ImageDraw) -> None:
    """A check mark: every box accounted for."""
    _line(draw, [(11.5, 13), (14.6, 15), (20.5, 10.6)])


ICONS: dict[str, Callable[[ImageDraw.ImageDraw], None]] = {
    "wiredbench": pulse,
    "trace": trace,
    "sandbox": sandbox,
    "presets": presets,
    "parity": parity,
}


GLYPH = 14
WHITE = "#ffffff"


def _glyph(paint: Callable[[ImageDraw.ImageDraw, float], None]) -> Image.Image:
    """A small white sign for an icon button, drawn on a 14 x 14 grid."""
    k = SCALE * 2
    image = Image.new("RGBA", (GLYPH * k, GLYPH * k), (0, 0, 0, 0))
    paint(ImageDraw.Draw(image), k)

    return image.resize((GLYPH, GLYPH), Image.Resampling.LANCZOS)


def glyph_delete(draw: ImageDraw.ImageDraw, k: float) -> None:
    """A bin: its lid, handle and body."""
    draw.rectangle((2 * k, 3 * k, 12 * k, 4.4 * k), fill=WHITE)
    draw.rectangle((5.5 * k, 1.5 * k, 8.5 * k, 3 * k), fill=WHITE)
    draw.polygon([(3.2 * k, 5.2 * k), (10.8 * k, 5.2 * k), (10 * k, 12.6 * k), (4 * k, 12.6 * k)], fill=WHITE)


def glyph_refresh(draw: ImageDraw.ImageDraw, k: float) -> None:
    """A circling arrow."""
    draw.arc((2 * k, 2 * k, 12 * k, 12 * k), 40, 330, fill=WHITE, width=round(1.8 * k))
    draw.polygon([(12.6 * k, 1.2 * k), (12.6 * k, 6.4 * k), (7.6 * k, 4.6 * k)], fill=WHITE)


GLYPHS: dict[str, Callable[[ImageDraw.ImageDraw, float], None]] = {
    "icon-delete": glyph_delete,
    "icon-refresh": glyph_refresh,
}


def draw(sign: Callable[[ImageDraw.ImageDraw], None], size: int = SIZE) -> Image.Image:
    image = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    _tile(canvas)
    sign(canvas)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    for name, sign in ICONS.items():
        draw(sign).save(OUT / f"{name}.png")
        print(f"wrote {OUT / f'{name}.png'}")

    for name, paint in GLYPHS.items():
        _glyph(paint).save(OUT / f"{name}.png")
        print(f"wrote {OUT / f'{name}.png'}")


if __name__ == "__main__":
    main()
