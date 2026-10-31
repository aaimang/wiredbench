"""Furnidata updates: check, store as a version, review, apply, roll back."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import case, func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from wiredbench.config import Settings
from wiredbench.errors import ApiError, not_found
from wiredbench.models import CatalogItem, CatalogVersion, GamedataState, utcnow
from wiredbench.services import furnidata
from wiredbench.services.upstream import Upstream, UpstreamError, furnidata_url

log = logging.getLogger("wiredbench.catalog")

VERSIONS_KEPT = 5
TYPE_ORDER = case(
    {
        name: rank
        for rank, name in enumerate(("trigger", "effect", "condition", "selector", "addon", "variable"))
    },
    value=CatalogItem.wired_type,
    else_=9,
)


class CatalogService:
    def __init__(self, settings: Settings, sessions: sessionmaker[Any], upstream: Upstream) -> None:
        self.settings = settings
        self.sessions = sessions
        self.upstream = upstream
        self._locks: dict[str, threading.Lock] = {}
        self._last_manual: dict[str, float] = {}
        self._guard = threading.Lock()

    # --- Checking for updates ---

    def cooldown_remaining(self, hotel: str) -> int:
        last = self._last_manual.get(hotel)
        if last is None:
            return 0
        return max(0, math.ceil(last + self.settings.sync_cooldown_seconds - time.monotonic()))

    def _lock_for(self, hotel: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(hotel, threading.Lock())

    def sync(self, hotel: str, force: bool = False, manual: bool = True) -> dict[str, Any]:
        """Checks one hotel. A failure at any step leaves the current version untouched."""
        if manual and (remaining := self.cooldown_remaining(hotel)):
            raise ApiError(
                429, "sync_cooldown", f"Wait {remaining} seconds before checking again.", remaining
            )
        lock = self._lock_for(hotel)
        if not lock.acquire(blocking=False):
            raise ApiError(409, "sync_running", "A check for this hotel is already running.")
        try:
            if manual:
                self._last_manual[hotel] = time.monotonic()
            return self._sync_locked(hotel, force)
        finally:
            lock.release()

    def _sync_locked(self, hotel: str, force: bool) -> dict[str, Any]:
        with self.sessions() as db:
            current = self._current(db, hotel)
            etag = current.etag if current and not force else None
        try:
            fetched = self.upstream.get(
                furnidata_url(hotel), self.settings.max_gamedata_mb * 2**20, etag=etag
            )
            if fetched.status == 304:
                self._record(hotel, "up_to_date", None)
                return {"result": "up_to_date", "version_id": current.id if current else None}
            if fetched.status != 200:
                raise UpstreamError(f"Habbo answered with HTTP {fetched.status}.")
            sha = hashlib.sha256(fetched.body).hexdigest()
            if current and current.sha256 == sha:
                with self.sessions.begin() as db:
                    db.execute(
                        update(CatalogVersion)
                        .where(CatalogVersion.id == current.id)
                        .values(etag=fetched.etag)
                    )
                self._record(hotel, "up_to_date", None)
                return {"result": "up_to_date", "version_id": current.id}
            version_id = self._store(hotel, sha, fetched.body, fetched.etag)
        except (UpstreamError, furnidata.InvalidFurnidata) as exc:
            self._record(hotel, "failed", str(exc))
            code = (
                "invalid_furnidata" if isinstance(exc, furnidata.InvalidFurnidata) else "upstream_unavailable"
            )
            raise ApiError(502, code, f"{exc} Your current catalogue was not changed.") from exc
        self._record(hotel, "update_available", None)
        return {"result": "first_import" if current is None else "update_available", "version_id": version_id}

    def _store(self, hotel: str, sha: str, body: bytes, etag: str | None) -> int:
        with self.sessions.begin() as db:
            existing = db.scalar(
                select(CatalogVersion).where(CatalogVersion.hotel == hotel, CatalogVersion.sha256 == sha)
            )
            if existing:
                # Seen before, such as a dismissed update or a rollback target. A manual check offers it again.
                if existing.status in ("dismissed", "archived"):
                    existing.status = "pending"
                existing.etag = etag
                existing_id: int = existing.id
                return existing_id

        parsed = furnidata.parse(body)
        raw_path = self._write_raw(hotel, sha, body)
        try:
            with self.sessions.begin() as db:
                current = self._current(db, hotel)
                known: set[str] = (
                    set(db.scalars(select(CatalogItem.classname).where(CatalogItem.version_id == current.id)))
                    if current
                    else set()
                )
                version = CatalogVersion(
                    hotel=hotel,
                    sha256=sha,
                    etag=etag,
                    status="pending",
                    base_version_id=current.id if current else None,
                    item_count=len(parsed.items),
                    wired_count=parsed.wired_count,
                    skipped_count=parsed.skipped,
                    raw_path=str(raw_path),
                )
                db.add(version)
                db.flush()
                db.execute(
                    insert(CatalogItem),
                    [
                        {
                            **item,
                            "version_id": version.id,
                            "is_new": bool(current and item["classname"] not in known),
                        }
                        for item in parsed.items
                    ],
                )
                version_id: int = version.id
                return version_id
        except Exception:
            raw_path.unlink(missing_ok=True)
            raise

    def _write_raw(self, hotel: str, sha: str, body: bytes) -> Path:
        folder = self.settings.gamedata_dir / hotel
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{sha}.json.gz"
        temp = folder / f".{uuid4().hex}.tmp"
        try:
            temp.write_bytes(gzip.compress(body, compresslevel=6))
            os.replace(temp, target)  # Atomic, so a crash never leaves half a file under the real name.
        finally:
            temp.unlink(missing_ok=True)
        return target

    def _record(self, hotel: str, result: str, error: str | None) -> None:
        with self.sessions.begin() as db:
            state = db.get(GamedataState, hotel) or GamedataState(hotel=hotel)
            state.last_checked_at = utcnow()
            state.last_result = result
            state.last_error = error
            db.add(state)

    # --- Applying ---

    def _current(self, db: Session, hotel: str) -> CatalogVersion | None:
        return db.scalar(
            select(CatalogVersion).where(CatalogVersion.hotel == hotel, CatalogVersion.status == "current")
        )

    def _version(self, db: Session, version_id: int) -> CatalogVersion:
        version = db.get(CatalogVersion, version_id)
        if version is None:
            raise not_found("Catalogue version")
        return version

    def apply(self, version_id: int, allowed: tuple[str, ...] = ("pending", "dismissed")) -> CatalogVersion:
        """One transaction, so readers see the old version or the new one and never a mix."""
        removed_files: list[str] = []
        with self.sessions.begin() as db:
            version = self._version(db, version_id)
            if version.status not in allowed:
                raise ApiError(409, "invalid_version_state", f"This version is {version.status}.")
            db.execute(
                update(CatalogVersion)
                .where(
                    CatalogVersion.hotel == version.hotel,
                    CatalogVersion.id != version.id,
                    CatalogVersion.status.in_(("current", "pending")),
                )
                .values(status="archived")
            )
            db.flush()
            version.status = "current"
            version.applied_at = utcnow()
            db.flush()
            removed_files = self._prune(db, version.hotel)
        for path in removed_files:
            with contextlib.suppress(OSError):
                Path(path).unlink(missing_ok=True)
        return version

    def rollback(self, version_id: int) -> CatalogVersion:
        return self.apply(version_id, allowed=("archived",))

    def dismiss(self, version_id: int) -> None:
        with self.sessions.begin() as db:
            version = self._version(db, version_id)
            if version.status != "pending":
                raise ApiError(409, "invalid_version_state", f"This version is {version.status}.")
            version.status = "dismissed"

    def _prune(self, db: Session, hotel: str) -> list[str]:
        versions = list(
            db.scalars(
                select(CatalogVersion)
                .where(CatalogVersion.hotel == hotel, CatalogVersion.status != "current")
                .order_by(CatalogVersion.id.desc())
            )
        )
        stale = versions[VERSIONS_KEPT - 1 :]
        paths = [version.raw_path for version in stale]
        for version in stale:
            db.delete(version)
        return paths

    # --- Reading ---

    def status(self, hotel: str) -> dict[str, Any]:
        with self.sessions() as db:
            versions = list(
                db.scalars(
                    select(CatalogVersion)
                    .where(CatalogVersion.hotel == hotel)
                    .order_by(CatalogVersion.id.desc())
                )
            )
            state = db.get(GamedataState, hotel)
            waiting = db.scalars(select(CatalogVersion.hotel).where(CatalogVersion.status == "pending")).all()
        current = next((v for v in versions if v.status == "current"), None)
        pending = next((v for v in versions if v.status == "pending"), None)
        return {
            "hotel": hotel,
            "current": version_dict(current) if current else None,
            "pending": version_dict(pending) if pending else None,
            "versions": [version_dict(v) for v in versions],
            "last_checked_at": state.last_checked_at if state else None,
            "last_result": state.last_result if state else None,
            "last_error": state.last_error if state else None,
            "updates_waiting": sorted(set(waiting)),
            "cooldown_seconds": self.cooldown_remaining(hotel),
        }

    def diff(self, from_id: int, to_id: int) -> list[dict[str, Any]]:
        """from_id 0 means an empty catalogue, which is how a first import is shown."""
        with self.sessions() as db:
            target = self._version(db, to_id)
            if from_id != 0 and self._version(db, from_id).hotel != target.hotel:
                raise ApiError(400, "different_hotels", "Versions from different hotels cannot be compared.")
            return furnidata.diff(
                self._items_data(db, from_id) if from_id else {}, self._items_data(db, to_id)
            )

    def _items_data(self, db: Session, version_id: int) -> dict[str, dict[str, Any]]:
        rows = db.execute(
            select(CatalogItem.classname, CatalogItem.data).where(CatalogItem.version_id == version_id)
        )
        return {row.classname: row.data for row in rows}

    def search(
        self,
        hotel: str,
        q: str = "",
        scope: str = "wired",
        wired_type: str | None = None,
        stage: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        with self.sessions() as db:
            current = self._current(db, hotel)
            if current is None:
                return {"version": None, "items": [], "total": 0, "facets": {}}
            base = [CatalogItem.version_id == current.id]
            if scope == "wired":
                base.append(CatalogItem.is_wired.is_(True))
            for word in q.split()[:8]:
                pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                base.append(
                    CatalogItem.classname.like(pattern, escape="\\")
                    | CatalogItem.name.like(pattern, escape="\\")
                    | CatalogItem.description.like(pattern, escape="\\")
                )
            facets = dict(
                db.execute(
                    select(CatalogItem.wired_type, func.count())
                    .where(*base, CatalogItem.wired_type.is_not(None))
                    .group_by(CatalogItem.wired_type)
                ).all()
            )
            where = list(base)
            if wired_type:
                where.append(CatalogItem.wired_type == wired_type)
            if stage:
                where.append(
                    CatalogItem.is_new.is_(True) if stage == "new" else CatalogItem.release_stage == stage
                )
            total = db.scalar(select(func.count()).select_from(CatalogItem).where(*where)) or 0
            rows = db.scalars(
                select(CatalogItem)
                .where(*where)
                .order_by(CatalogItem.is_wired.desc(), TYPE_ORDER, CatalogItem.classname)
                .offset(offset)
                .limit(limit)
            ).all()
            return {
                "version": version_dict(current),
                "items": [item_dict(item) for item in rows],
                "total": total,
                "facets": facets,
            }

    def item(self, hotel: str, classname: str) -> dict[str, Any]:
        with self.sessions() as db:
            current = self._current(db, hotel)
            row = None
            if current:
                row = db.scalar(
                    select(CatalogItem).where(
                        CatalogItem.version_id == current.id, CatalogItem.classname == classname
                    )
                )
            if row is None:
                raise not_found("Furni")
            return {**item_dict(row), "data": row.data, "version_id": current.id if current else None}

    def item_exists(self, classname: str, revision: int) -> bool:
        with self.sessions() as db:
            found = db.scalar(
                select(CatalogItem.id)
                .where(CatalogItem.classname == classname, CatalogItem.revision == revision)
                .limit(1)
            )
            return found is not None

    def current_sha(self, hotel: str) -> str | None:
        with self.sessions() as db:
            current = self._current(db, hotel)
            return current.sha256 if current else None

    def hotels_in_use(self) -> list[str]:
        with self.sessions() as db:
            return list(db.scalars(select(CatalogVersion.hotel).where(CatalogVersion.status == "current")))


def version_dict(version: CatalogVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "hotel": version.hotel,
        "sha256": version.sha256,
        "status": version.status,
        "base_version_id": version.base_version_id,
        "fetched_at": version.fetched_at,
        "applied_at": version.applied_at,
        "item_count": version.item_count,
        "wired_count": version.wired_count,
        "skipped_count": version.skipped_count,
    }


def item_dict(item: CatalogItem) -> dict[str, Any]:
    return {
        "classname": item.classname,
        "kind": item.kind,
        "furni_id": item.furni_id,
        "revision": item.revision,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "furniline": item.furniline,
        "xdim": item.xdim,
        "ydim": item.ydim,
        "height": item.height,
        "is_wired": item.is_wired,
        "wired_type": item.wired_type,
        "release_stage": item.release_stage,
        "is_new": item.is_new,
    }
