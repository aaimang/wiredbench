"""Furni asset cache on disk. Files are fetched on first use and removed oldest-used first."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from uuid import uuid4

from wiredbench.services.upstream import Upstream, UpstreamError, icon_url

MAX_ICON_BYTES = 2**20
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MISSING_RETRY_SECONDS = 24 * 3600


class AssetCache:
    def __init__(self, root: Path, upstream: Upstream) -> None:
        self.root = root
        self.upstream = upstream
        self._downloads = threading.Semaphore(4)  # A page of icons must not flood Habbo.

    def _folder(self, revision: int, classname: str) -> Path:
        # Classnames are checked against the catalogue first; this only makes * safe on Windows.
        return self.root / str(revision) / classname.replace("*", "_")

    def icon(self, revision: int, classname: str) -> Path | None:
        """The cached icon, or None if Habbo has none. Raises UpstreamError if Habbo cannot be reached."""
        folder = self._folder(revision, classname)
        path = folder / "icon.png"
        if path.exists():
            os.utime(path)  # Marks it recently used.
            return path
        missing = folder / "icon.missing"
        if missing.exists() and time.time() - missing.stat().st_mtime < MISSING_RETRY_SECONDS:
            return None
        with self._downloads:
            fetched = self.upstream.get(icon_url(revision, classname), MAX_ICON_BYTES)
        folder.mkdir(parents=True, exist_ok=True)
        if fetched.status == 404:
            missing.touch()
            return None
        if fetched.status != 200 or not fetched.body.startswith(PNG_MAGIC):
            raise UpstreamError(f"Unexpected icon response: HTTP {fetched.status}.")
        temp = folder / f".{uuid4().hex}.tmp"
        temp.write_bytes(fetched.body)
        os.replace(temp, path)
        return path

    def _files(self) -> list[Path]:
        return [p for p in self.root.rglob("*") if p.is_file()] if self.root.exists() else []

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
