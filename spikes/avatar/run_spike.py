"""Spike: can habbo-imaging supply avatar animation frames for the room view?

Usage: run_spike.py <output_dir>
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"
FIGURE = "hd-180-1.ch-210-66.lg-270-82.sh-290-91.hr-100-61"
HOTELS = ["com", "com.br", "de", "es", "fi", "fr", "it", "nl", "com.tr", "sandbox"]


def host(hotel: str) -> str:
    return "https://sandbox.habbo.com" if hotel == "sandbox" else f"https://www.habbo.{hotel}"


def get(url: str) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, res.read(4_000_000), res.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", exc.headers.get("Content-Type", "")


def avatar(hotel: str = "com", **params) -> tuple[int, bytes]:
    query = {"figure": FIGURE, "size": "m", "direction": 2, "head_direction": 2, **params}
    status, body, _ = get(f"{host(hotel)}/habbo-imaging/avatarimage?{urllib.parse.urlencode(query)}")
    time.sleep(0.1)
    return status, body


def digest(body: bytes) -> str:
    return hashlib.sha1(body).hexdigest()[:10]


def main() -> None:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    result: dict = {"hotels": {}, "actions": {}, "frames": {}, "directions": {}, "other": {}}

    for hotel in HOTELS:
        status, body = avatar(hotel)
        user_status, user_body, _ = get(f"{host(hotel)}/api/public/users?name=Habbo")
        result["hotels"][hotel] = {
            "imaging": status,
            "bytes": len(body),
            "users_api": user_status,
            "user_has_figure": b"figureString" in user_body,
        }

    baseline = digest(avatar()[1])
    tiles = []
    for action in ["std", "wlk", "sit", "lay", "wav", "crr", "drk", "snk", "sig", "respect"]:
        status, body = avatar(action=action)
        result["actions"][action] = {"status": status, "differs_from_std": digest(body) != baseline}
        if status == 200:
            tiles.append((action, body))

    for action in ["wlk", "wav", "std"]:
        hashes = []
        for frame in range(8):
            status, body = avatar(action=action, frame=frame)
            hashes.append(digest(body) if status == 200 else f"http{status}")
            if action == "wlk" and frame < 4 and status == 200:
                tiles.append((f"wlk frame={frame}", body))
        result["frames"][action] = {"hashes": hashes, "distinct": len(set(hashes))}

    for gesture in ["std", "sml", "agr", "sad", "srp", "spk", "eyb"]:
        status, body = avatar(gesture=gesture)
        result["other"][f"gesture_{gesture}"] = {"status": status, "differs": digest(body) != baseline}
    for label, params in {
        "headonly": {"headonly": 1},
        "size_s": {"size": "s"},
        "size_l": {"size": "l"},
        "effect": {"effect": 1},
        "action_combo": {"action": "wlk,wav"},
        "hand_item": {"action": "crr=1"},
        "user_param": {"user": "Habbo", "figure": ""},
    }.items():
        status, body = avatar(**params)
        size = Image.open(io.BytesIO(body)).size if status == 200 and body else None
        result["other"][label] = {"status": status, "differs": digest(body) != baseline, "size": size}

    hashes = set()
    for direction in range(8):
        status, body = avatar(direction=direction, head_direction=direction)
        hashes.add(digest(body))
        result["directions"][direction] = status
        tiles.append((f"dir {direction}", body))
    result["directions"]["distinct"] = len(hashes)

    cell = 90
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell, rows * (cell + 40)), (244, 239, 230, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, body) in enumerate(tiles):
        image = Image.open(io.BytesIO(body)).convert("RGBA")
        x, y = (i % cols) * cell, (i // cols) * (cell + 40)
        sheet.alpha_composite(image, dest=(x + 12, y + 2))
        draw.text((x + 3, y + cell + 24), name, fill=(38, 33, 28, 255))
    sheet.save(output / "avatar_sheet.png")
    (output / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
