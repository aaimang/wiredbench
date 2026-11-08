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


# Action, gesture and frame, as the image service takes them.
POSES = [
    ("std", "std", 0),
    ("wlk", "std", 0),
    ("wlk", "std", 1),
    ("wlk", "std", 2),
    ("wlk", "std", 3),
    ("sit", "std", 0),
    ("lay", "std", 0),
    ("wav", "std", 0),
    ("wav", "std", 1),
    ("blw", "std", 0),
    ("blw", "std", 1),
    ("respect", "std", 0),
    ("sig=6", "std", 0),
    ("crr=6", "std", 0),
    ("drk=6", "std", 0),
    ("sit,wav", "std", 0),
    ("wlk,crr=6", "std", 1),
    ("std", "sml", 0),
    ("std", "agr", 0),
    ("std", "sad", 0),
    ("std", "srp", 0),
    ("std", "spk", 0),
    ("std", "spk", 1),
    ("std", "eyb", 0),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--poses", action="store_true", help="Check every pose, action and gesture too.")
    parser.add_argument("--directions", default="0,1,2,3,4,5,6,7")
    parser.add_argument("figures", nargs="*")
    args = parser.parse_args()
    upstream = Upstream(httpx.HTTPTransport())
    figures = Figures(args.cache, upstream)
    directions = [int(d) for d in args.directions.split(",")]
    poses = POSES if args.poses else POSES[:1]
    by_pose: dict[str, list[float]] = {}
    for figure in args.figures or FIGURES:
        for action, gesture, frame in poses:
            for direction in directions:
                drawn = figures.draw("com", figure, direction, direction, action, gesture, frame)
                time.sleep(0.15)
                query = urlencode(
                    {
                        "figure": figure,
                        "size": "m",
                        "direction": direction,
                        "head_direction": direction,
                        "action": action,
                        "gesture": gesture,
                        "frame": frame,
                    }
                )
                theirs = upstream.get(f"https://www.habbo.com/habbo-imaging/avatarimage?{query}", 2**20)
                name = f"{action}/{gesture}/{frame}"
                if drawn is None or theirs.status != 200:
                    print(
                        f"{name} d{direction}: " + ("not drawn" if drawn is None else f"HTTP {theirs.status}")
                    )
                    continue
                ours, habbo = Image.open(io.BytesIO(drawn)), Image.open(io.BytesIO(theirs.body))
                if ours.size != habbo.size:
                    print(f"{name} d{direction}: size {ours.size} against {habbo.size}")
                    by_pose.setdefault(name, []).append(0.0)
                    continue
                if direction % 2 and ("sit" in action or "lay" in action):
                    continue  # Habbo never sits or lies diagonally, and its image service draws a stander.
                score, wrong = matched(ours, habbo)
                by_pose.setdefault(name, []).append(score)
                if score < 97 and direction != 7:  # Habbo's own direction 7 image has the wrong hair.
                    print(f"{score:6.2f}% d{direction} {name} {figure}")
                if args.out:
                    args.out.mkdir(parents=True, exist_ok=True)
                    width, height = ours.size
                    pair = Image.new("RGBA", (width * 2, height), (255, 255, 255, 255))
                    pair.alpha_composite(ours.convert("RGBA"), (0, 0))
                    pair.alpha_composite(habbo.convert("RGBA"), (width, 0))
                    label = name.replace("/", "_").replace(",", "+").replace("=", "")
                    pair.resize((width * 8, height * 4), Image.Resampling.NEAREST).save(
                        args.out / f"{label}_d{direction}_{abs(hash(figure)) % 1000}.png"
                    )
    every = [score for scores in by_pose.values() for score in scores]
    for name, scores in by_pose.items():
        print(f"{sum(scores) / len(scores):6.2f}% average, lowest {min(scores):6.2f}%  {name}")
    if every:
        print(f"average {sum(every) / len(every):.2f}% over {len(every)} images, lowest {min(every):.2f}%")


if __name__ == "__main__":
    main()
