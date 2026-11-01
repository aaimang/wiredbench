"""What each @handitem value looks like, from the two files Habbo's own client loads.

HabboAvatarActions.xml maps a hand item ID to the number of its art, which is a different number. The
avatar image service only knows art numbers, and does not have the newest art, so those items are
drawn here from hh_human_item.swf. Nothing is stored in the repo: both files are fetched on first use.
"""

from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET  # noqa: S405 - Only for the error type. defusedxml does the parsing.
from dataclasses import dataclass
from pathlib import Path

from defusedxml.ElementTree import fromstring as safe_fromstring
from PIL import Image

from wiredbench.config import HOTELS
from wiredbench.services import swf
from wiredbench.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)

MAX_VARIABLES_BYTES = 8 * 2**20
MAX_FILE_BYTES = 16 * 2**20
RETRY_SECONDS = 300
CHECK_SECONDS = 24 * 3600
CLIENT_URL = "flash.client.url="
# Measured against the image service in all poses: the item is behind the body in these directions.
BEHIND_BODY = frozenset({0, 1, 5, 6, 7})
# The image service's canvas puts Habbo's offset origin at this height.
ORIGIN_Y = 100


@dataclass
class _Build:
    name: str
    default: int
    arts: dict[int, int]
    images: dict[str, Image.Image]
    offsets: dict[str, tuple[int, int]]


def _parse_actions(body: bytes) -> tuple[int, dict[int, int]]:
    root = safe_fromstring(body)
    for action in root.iter("action"):
        if action.get("id") != "CarryItem":
            continue
        default, arts = 0, {}
        for param in action.findall("param"):
            key, value = param.get("id", ""), param.get("value", "")
            try:
                if key == "default":
                    default = int(value)
                else:
                    arts[int(key)] = int(value)
            except ValueError:
                continue
        return default, arts
    raise ValueError("No CarryItem action.")


def _parse_art(body: bytes) -> tuple[dict[str, Image.Image], dict[str, tuple[int, int]]]:
    parsed = swf.parse(body)
    images: dict[str, Image.Image] = {}
    for name, image in parsed.named_images().items():
        start = name.find("h_crr_ri_")
        if start >= 0:
            images[name[start:]] = image.convert("RGBA")
    offsets: dict[str, tuple[int, int]] = {}
    for binary in parsed.binaries.values():
        if b"<manifest" not in binary[:200]:
            continue
        for asset in safe_fromstring(binary).iter("asset"):
            name, param = asset.get("name", ""), asset.find("param")
            if not name.startswith("h_crr_ri_") or param is None:
                continue
            x, _, y = param.get("value", "").partition(",")
            try:
                offsets[name] = (int(x), int(y))
            except ValueError:
                continue
    return images, offsets


class HandItems:
    def __init__(self, root: Path, upstream: Upstream) -> None:
        self.root = root
        self.upstream = upstream
        self._lock = threading.Lock()
        self._builds: dict[str, _Build] = {}
        self._hotels: dict[str, tuple[float, str | None]] = {}

    def _file(self, base: str, build: str, name: str) -> bytes:
        path = self.root / build / name
        if path.exists():
            return path.read_bytes()
        fetched = self.upstream.get(f"{base}{name}", MAX_FILE_BYTES)
        if fetched.status != 200:
            raise UpstreamError(f"Unexpected {name} response: HTTP {fetched.status}.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(fetched.body)
        temp.replace(path)
        return fetched.body

    def _load(self, hotel: str) -> _Build | None:
        with self._lock:
            checked, name = self._hotels.get(hotel, (0.0, None))
            wait = CHECK_SECONDS if name else RETRY_SECONDS
            if time.monotonic() - checked < wait and checked:
                return self._builds.get(name) if name else None
            self._hotels[hotel] = (time.monotonic(), None)
            try:
                fetched = self.upstream.get(
                    f"https://{HOTELS[hotel]}/gamedata/external_variables/1", MAX_VARIABLES_BYTES
                )
                base = next(
                    line[len(CLIENT_URL) :].strip()
                    for line in fetched.body.decode("utf-8", "replace").splitlines()
                    if line.startswith(CLIENT_URL)
                )
                base = f"https:{base}" if base.startswith("//") else base
                base = base if base.endswith("/") else f"{base}/"
                name = base.rstrip("/").rsplit("/", 1)[1]
                if not name.replace("-", "").replace("_", "").isalnum():
                    raise ValueError("Unexpected client folder.")
                if name not in self._builds:
                    default, arts = _parse_actions(self._file(base, name, "HabboAvatarActions.xml"))
                    images, offsets = _parse_art(self._file(base, name, "hh_human_item.swf"))
                    self._builds = {name: _Build(name, default, arts, images, offsets)}
            except (UpstreamError, ValueError, StopIteration, ET.ParseError, OSError) as exc:
                log.warning("Hand item files are unavailable for %s: %s", hotel, exc)
                return None
            self._hotels[hotel] = (time.monotonic(), name)
            return self._builds[name]

    def art(self, hotel: str, hand_item: int) -> int | None:
        """The art number to draw, -1 for an ID that draws nothing, or None if the map cannot be read.

        An ID missing from the map uses the file's default, as the map itself says to.
        """
        build = self._load(hotel)
        if build is None:
            return None
        return build.arts.get(hand_item, build.default)

    def has_art(self, hotel: str, art: int) -> bool:
        build = self._load(hotel)
        return build is not None and any(f"h_crr_ri_{art}_{d}_0" in build.images for d in range(8))

    def draw(self, hotel: str, avatar: Image.Image, art: int, direction: int) -> Image.Image:
        """The item in the avatar's hand, on an image of the avatar holding nothing."""
        build = self._load(hotel)
        key = f"h_crr_ri_{art}_{direction}_0"
        if build is None or key not in build.images or key not in build.offsets:
            return avatar
        x, y = build.offsets[key]
        item = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
        item.paste(build.images[key], (-x, ORIGIN_Y - y))
        canvas = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
        layers = (item, avatar) if direction in BEHIND_BODY else (avatar, item)
        for layer in layers:
            canvas.alpha_composite(layer.convert("RGBA"))
        return canvas
