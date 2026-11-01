"""Asset cache on disk: furni icons and sprites, and avatar frames.

Files are fetched on first use and removed oldest-used first.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import uuid4

from PIL import Image

from wiredbench.config import HOTELS
from wiredbench.services import swf
from wiredbench.services.handitems import HandItems
from wiredbench.services.upstream import IMAGE_HOST, Upstream, UpstreamError, icon_url

MAX_ICON_BYTES = 2**20
MAX_AVATAR_BYTES = 2 * 2**20
MAX_PROFILE_BYTES = 2**18
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MISSING_RETRY_SECONDS = 24 * 3600

FIGURE = re.compile(r"[a-z]{2}-\d{1,6}(-\d{1,6}){0,3}(\.[a-z]{2}-\d{1,6}(-\d{1,6}){0,3}){0,24}")
CARRY = re.compile(r"^crr=(\d+)$")
NO_ART = 9999  # The image service draws the raised hand with nothing in it.
HABBO_NAME = re.compile(r"[\w.,:;=?!@+-]{1,32}")


def _write_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


MANIFEST_NAME = f"manifest.v{swf.ART_VERSION}.json"
ATLAS_NAME = f"atlas.v{swf.ART_VERSION}.png"


class AssetCache:
    def __init__(self, root: Path, upstream: Upstream) -> None:
        self.root = root
        self.avatar_root = root.parent / "avatars"
        self.upstream = upstream
        self._downloads = threading.Semaphore(4)  # A page of icons must not flood Habbo.
        self.hand_items = HandItems(root.parent / "handitems", upstream)
        self._service_has_art: dict[int, bool] = {}

    def _folder(self, revision: int, classname: str) -> Path:
        # Classnames are checked against the catalogue first; this only makes * safe on Windows.
        return self.root / str(revision) / classname.replace("*", "_")

    def _is_known_missing(self, marker: Path) -> bool:
        return marker.exists() and time.time() - marker.stat().st_mtime < MISSING_RETRY_SECONDS

    def icon(self, revision: int, classname: str) -> Path | None:
        """The cached icon, or None if Habbo has none. Raises UpstreamError if Habbo cannot be reached."""
        folder = self._folder(revision, classname)
        path = folder / "icon.png"
        if path.exists():
            os.utime(path)  # Marks it recently used.
            return path
        missing = folder / "icon.missing"
        if self._is_known_missing(missing):
            return None
        with self._downloads:
            fetched = self.upstream.get(icon_url(revision, classname), MAX_ICON_BYTES)
        folder.mkdir(parents=True, exist_ok=True)
        if fetched.status == 404:
            missing.touch()
            return None
        if fetched.status != 200 or not fetched.body.startswith(PNG_MAGIC):
            raise UpstreamError(f"Unexpected icon response: HTTP {fetched.status}.")
        _write_atomic(path, fetched.body)
        return path

    def cached_states(self, revision: int, classname: str) -> list[int] | None:
        """A furni's states from art already on disk. Never downloads, because a room is about to run."""
        manifest = self._folder(revision, classname.split("*")[0]) / MANIFEST_NAME
        try:
            states = json.loads(manifest.read_text()).get("states")
        except (OSError, ValueError):
            return None
        return states if isinstance(states, list) and all(isinstance(s, int) for s in states) else None

    def furni(self, revision: int, classname: str) -> tuple[Path, Path] | None:
        """Manifest and atlas paths, built on first use. None if the furni cannot be drawn."""
        base = classname.split("*")[0]  # Colour variants share one SWF.
        folder = self._folder(revision, base)
        manifest, atlas = folder / MANIFEST_NAME, folder / ATLAS_NAME
        if manifest.exists() and atlas.exists():
            os.utime(manifest)
            os.utime(atlas)
            return manifest, atlas
        missing = folder / "furni.missing"
        if self._is_known_missing(missing):
            return None
        with self._downloads:
            url = f"https://{IMAGE_HOST}/dcr/hof_furni/{revision}/{quote(base)}.swf"
            fetched = self.upstream.get(url, swf.MAX_SWF_BYTES)
        folder.mkdir(parents=True, exist_ok=True)
        if fetched.status == 404:
            missing.touch()
            return None
        if fetched.status != 200:
            raise UpstreamError(f"Unexpected furni response: HTTP {fetched.status}.")
        try:
            data, image = swf.build(fetched.body, base)
        except swf.SwfError:
            missing.touch()
            return None
        _write_atomic(atlas, image)
        _write_atomic(manifest, json.dumps(data, separators=(",", ":")).encode())
        return manifest, atlas

    def avatar(
        self, hotel: str, figure: str, action: str, gesture: str, direction: int, frame: int
    ) -> Path | None:
        """One cached avatar frame. All values must already be validated by the route."""
        action, art = self._translate_hand_item(hotel, action)
        query = {
            "figure": figure,
            "size": "m",
            "direction": direction,
            # Habbo draws the wrong hair for a head facing 7. Facing 6 looks right on that body.
            "head_direction": 6 if direction == 7 else direction,
            "action": action,
            "gesture": gesture,
            "frame": frame,
        }
        text = urlencode(query)
        folder = self.avatar_root / hotel
        path = folder / f"{hashlib.sha256(text.encode()).hexdigest()}.png"
        if path.exists():
            os.utime(path)
            return path
        with self._downloads:
            fetched = self.upstream.get(
                f"https://{HOTELS[hotel]}/habbo-imaging/avatarimage?{text}", MAX_AVATAR_BYTES
            )
        if fetched.status in (400, 404):
            return None
        if fetched.status != 200 or not fetched.body.startswith(PNG_MAGIC):
            raise UpstreamError(f"Unexpected avatar response: HTTP {fetched.status}.")
        body = fetched.body
        if art is not None and self._must_draw(hotel, figure, art):
            image = Image.open(io.BytesIO(body)).convert("RGBA")
            out = io.BytesIO()
            self.hand_items.draw(hotel, image, art, direction).save(out, "PNG")
            body = out.getvalue()
        folder.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, body)
        return path

    def _translate_hand_item(self, hotel: str, action: str) -> tuple[str, int | None]:
        """Swaps a @handitem value for its art number, or drops it if it draws nothing."""
        parts = action.split(",")
        for index, part in enumerate(parts):
            found = CARRY.match(part)
            if not found:
                continue
            art = self.hand_items.art(hotel, int(found[1]))
            if art is None:  # Habbo's map is unreachable, so this may be the wrong item, but it is held.
                return action, None
            if art < 0:
                rest = parts[:index] + parts[index + 1 :]
                return ",".join(rest) or "std", None
            parts[index] = f"crr={art}"
            return ",".join(parts), art
        return action, None

    def _must_draw(self, hotel: str, figure: str, art: int) -> bool:
        """True for art in Habbo's file that the image service does not have yet. Asked once per item."""
        known = self._service_has_art.get(art)
        if known is None:
            if not self.hand_items.has_art(hotel, art):
                return False
            known = False
            for direction in (2, 4):  # An item can be hidden behind the body in one of them.
                frames = [
                    self.upstream.get(
                        f"https://{HOTELS[hotel]}/habbo-imaging/avatarimage?"
                        + urlencode(
                            {
                                "figure": figure,
                                "size": "m",
                                "direction": direction,
                                "head_direction": direction,
                                "action": f"crr={number}",
                            }
                        ),
                        MAX_AVATAR_BYTES,
                    ).body
                    for number in (art, NO_ART)
                ]
                known = known or frames[0] != frames[1]
            self._service_has_art[art] = known
        return not known

    def lookup_figure(self, hotel: str, name: str) -> dict[str, str] | None:
        """Finds a Habbo's look by name. Not cached, because looks change."""
        url = f"https://{HOTELS[hotel]}/api/public/users?{urlencode({'name': name})}"
        fetched = self.upstream.get(url, MAX_PROFILE_BYTES)
        if fetched.status == 404:
            return None
        if fetched.status != 200:
            raise UpstreamError(f"Unexpected profile response: HTTP {fetched.status}.")
        try:
            profile = json.loads(fetched.body)
            found, figure = str(profile["name"]), str(profile["figureString"])
        except (ValueError, KeyError, TypeError) as exc:
            raise UpstreamError("Unexpected profile response.") from exc
        if not FIGURE.fullmatch(figure):
            raise UpstreamError("Unexpected profile response.")
        return {"name": found[:32], "figure": figure}

    def _files(self) -> list[Path]:
        return [
            p
            for root in (self.root, self.avatar_root)
            if root.exists()
            for p in root.rglob("*")
            if p.is_file()
        ]

    def size_bytes(self) -> int:
        return sum(p.stat().st_size for p in self._files())

    def enforce_limit(self, limit_bytes: int) -> int:
        """Removes least recently used files until under the limit. Returns how many it removed."""
        files = sorted(self._files(), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        removed = 0
        for path in files:
            if total <= limit_bytes:
                break
            total -= path.stat().st_size
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def clear(self) -> int:
        return self.enforce_limit(-1)
