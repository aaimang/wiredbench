#!/usr/bin/env python3
"""Compares avatars drawn from their parts with Habbo's own images, pixel by pixel.

uv run python scripts/avatar_check.py --cache DIR [--out DIR] [FIGURE ...]

DIR keeps Habbo's files between runs, outside this repository. With --out, each pair and the
pixels that differ are saved there to look at.
"""

from __future__ import annotations

import argparse
import io
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from PIL import Image

from wiredbench.services.figures import Figures
from wiredbench.services.upstream import Upstream

FIGURES = [
    "hr-100-61.hd-180-1.ch-210-66.lg-270-82.sh-290-80",
    "hr-3090-45.hd-180-1.ch-210-66.lg-270-82.sh-290-80.ha-1010-62",
    "hr-3090-45.hd-180-1.ch-210-66.lg-270-82.sh-290-80.ea-3318-62",
    "hr-515-33.hd-600-1.ch-635-70.lg-716-66-62.sh-735-68",
    "hr-893-45.hd-209-8.ch-3030-110.lg-3023-110.sh-3068-1408-110.fa-1201.cc-3007-82-1408",
]


def matched(ours: Image.Image, theirs: Image.Image) -> tuple[float, int]:
    def clean(pixel: tuple[int, ...]) -> tuple[int, ...]:
        return (0, 0, 0, 0) if pixel[3] == 0 else pixel

    pairs = list(zip(ours.convert("RGBA").getdata(), theirs.convert("RGBA").getdata(), strict=True))
    same = sum(clean(a) == clean(b) for a, b in pairs)
    return 100 * same / len(pairs), len(pairs) - same


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("figures", nargs="*")
    args = parser.parse_args()
    upstream = Upstream(httpx.HTTPTransport())
    figures = Figures(args.cache, upstream)
    total = []
    for figure in args.figures or FIGURES:
        for direction in range(8):
            drawn = figures.draw("com", figure, direction, direction)
            time.sleep(0.2)
            query = urlencode(
                {
                    "figure": figure,
                    "size": "m",
                    "direction": direction,
                    "head_direction": direction,
                    "action": "std",
                }
            )
            theirs = upstream.get(f"https://www.habbo.com/habbo-imaging/avatarimage?{query}", 2**20)
            if drawn is None or theirs.status != 200:
                print(f"{figure} d{direction}: not drawn" if drawn is None else f"HTTP {theirs.status}")
                continue
            ours, habbo = Image.open(io.BytesIO(drawn)), Image.open(io.BytesIO(theirs.body))
            score, wrong = matched(ours, habbo)
            total.append(score)
            print(f"{score:6.2f}% {wrong:5d} px  d{direction}  {figure}")
            if args.out:
                args.out.mkdir(parents=True, exist_ok=True)
                pair = Image.new("RGBA", (128, 110), (255, 255, 255, 255))
                pair.alpha_composite(ours.convert("RGBA"), (0, 0))
                pair.alpha_composite(habbo.convert("RGBA"), (64, 0))
                pair.resize((512, 440), Image.Resampling.NEAREST).save(
                    args.out / f"{len(total):03d}_d{direction}.png"
                )
    if total:
        print(f"average {sum(total) / len(total):.2f}% over {len(total)} images, lowest {min(total):.2f}%")


if __name__ == "__main__":
    main()
