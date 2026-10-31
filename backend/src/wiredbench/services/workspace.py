"""Folders, sandboxes, version history and the trash."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from wiredbench.errors import ApiError, not_found
from wiredbench.models import Folder, Sandbox, SandboxVersion, utcnow

MAX_DEPTH = 12
VERSIONS_KEPT = 50
TRASH_DAYS = 30


def _live_folder(db: Session, folder_id: int) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise not_found("Folder")
    return folder


def live_sandbox(db: Session, sandbox_id: int) -> Sandbox:
    sandbox = db.get(Sandbox, sandbox_id)
    if sandbox is None or sandbox.deleted_at is not None:
        raise not_found("Sandbox")
    return sandbox


def _editable(sandbox: Sandbox) -> Sandbox:
    if sandbox.kind == "tutorial":
        raise ApiError(403, "tutorial_read_only", "Tutorials are read-only. Duplicate it to make changes.")
    return sandbox


def _name_taken(db: Session, name: str, folder_id: int | None, kind: str, exclude: int | None = None) -> bool:
    table = Folder if kind == "folder" else Sandbox
    parent = Folder.parent_id if kind == "folder" else Sandbox.folder_id
    query = (
        select(table.id)
        .where(func.lower(table.name) == name.lower(), parent == folder_id, table.deleted_at.is_(None))
        .limit(1)
    )
    if exclude is not None:
        query = query.where(table.id != exclude)
    return db.scalar(query) is not None


def _require_free(
    db: Session, name: str, folder_id: int | None, kind: str, exclude: int | None = None
) -> None:
    if _name_taken(db, name, folder_id, kind, exclude):
        raise ApiError(409, "name_taken", f"Something in this folder is already called “{name}”.")


def free_name(db: Session, name: str, folder_id: int | None, kind: str, suffix: str) -> str:
    candidate, count = name, 1
    while _name_taken(db, candidate, folder_id, kind):
        label = suffix if count == 1 else f"{suffix} {count}"
        candidate = f"{name[: 120 - len(label) - 3]} ({label})"
        count += 1
    return candidate


def _depth(db: Session, folder_id: int | None) -> int:
    depth = 0
    while folder_id is not None:
        depth += 1
        folder_id = db.scalar(select(Folder.parent_id).where(Folder.id == folder_id))
    return depth


def _subtree_height(db: Session, folder_id: int) -> int:
    children = db.scalars(
        select(Folder.id).where(Folder.parent_id == folder_id, Folder.deleted_at.is_(None))
    ).all()
    return 1 + max((_subtree_height(db, child) for child in children), default=0)


def tree(db: Session) -> dict[str, Any]:
    folders = db.scalars(
        select(Folder).where(Folder.deleted_at.is_(None)).order_by(func.lower(Folder.name))
    ).all()
    sandboxes = db.scalars(
        select(Sandbox).where(Sandbox.deleted_at.is_(None)).order_by(func.lower(Sandbox.name))
    ).all()
    return {
        "folders": [folder_dict(f) for f in folders],
        "sandboxes": [sandbox_summary(s) for s in sandboxes],
    }


def create_folder(db: Session, name: str, parent_id: int | None) -> Folder:
    if parent_id is not None:
        _live_folder(db, parent_id)
    if _depth(db, parent_id) >= MAX_DEPTH:
        raise ApiError(400, "too_deep", f"Folders can nest {MAX_DEPTH} levels deep.")
    _require_free(db, name, parent_id, "folder")
    folder = Folder(name=name, parent_id=parent_id)
    db.add(folder)
    db.flush()
    return folder


def update_folder(db: Session, folder_id: int, changes: dict[str, Any]) -> Folder:
    folder = _live_folder(db, folder_id)
    name = changes.get("name", folder.name)
    parent_id = changes.get("parent_id", folder.parent_id)
    if parent_id != folder.parent_id and parent_id is not None:
        _live_folder(db, parent_id)
        ancestor: int | None = parent_id
        while ancestor is not None:
            if ancestor == folder.id:
                raise ApiError(400, "folder_cycle", "A folder cannot move inside itself.")
            ancestor = db.scalar(select(Folder.parent_id).where(Folder.id == ancestor))
        if _depth(db, parent_id) + _subtree_height(db, folder.id) > MAX_DEPTH:
            raise ApiError(400, "too_deep", f"Folders can nest {MAX_DEPTH} levels deep.")
    _require_free(db, name, parent_id, "folder", exclude=folder.id)
    folder.name, folder.parent_id = name, parent_id
    db.flush()
    return folder


def trash_folder(db: Session, folder_id: int) -> None:
    root = _live_folder(db, folder_id)
    batch, now = uuid4().hex, utcnow()
    pending = [root.id]
    while pending:
        current = pending.pop()
        folder = db.get(Folder, current)
        if folder is None:
            continue
        folder.deleted_at, folder.trash_batch = now, batch
        pending.extend(
            db.scalars(select(Folder.id).where(Folder.parent_id == current, Folder.deleted_at.is_(None)))
        )
        for sandbox in db.scalars(
            select(Sandbox).where(Sandbox.folder_id == current, Sandbox.deleted_at.is_(None))
        ):
            sandbox.deleted_at, sandbox.trash_batch = now, batch
    root.trash_root = True
    db.flush()


def create_sandbox(
    db: Session, name: str, folder_id: int | None, description: str, hotel: str, catalog_sha: str | None
) -> Sandbox:
    if folder_id is not None:
        _live_folder(db, folder_id)
    _require_free(db, name, folder_id, "sandbox")
    sandbox = Sandbox(
        name=name,
        folder_id=folder_id,
        description=description,
        hotel=hotel,
        document={},
        catalog_sha256=catalog_sha,
    )
    db.add(sandbox)
    db.flush()
    db.add(SandboxVersion(sandbox_id=sandbox.id, revision=1, document={}))
    db.flush()
    return sandbox


def update_sandbox(db: Session, sandbox_id: int, changes: dict[str, Any]) -> Sandbox:
    sandbox = _editable(live_sandbox(db, sandbox_id))
    name = changes.get("name", sandbox.name)
    folder_id = changes.get("folder_id", sandbox.folder_id)
    if folder_id != sandbox.folder_id and folder_id is not None:
        _live_folder(db, folder_id)
    _require_free(db, name, folder_id, "sandbox", exclude=sandbox.id)
    sandbox.name, sandbox.folder_id = name, folder_id
    sandbox.description = changes.get("description", sandbox.description)
    db.flush()
    return sandbox


def save_document(
    db: Session, sandbox_id: int, document: dict[str, Any], base_revision: int, catalog_sha: str | None
) -> Sandbox:
    sandbox = _editable(live_sandbox(db, sandbox_id))
    if base_revision != sandbox.revision:
        raise ApiError(409, "revision_conflict", "This sandbox was changed elsewhere. Reload before saving.")
    sandbox.revision += 1
    sandbox.document = document
    sandbox.catalog_sha256 = catalog_sha
    db.add(SandboxVersion(sandbox_id=sandbox.id, revision=sandbox.revision, document=document))
    db.flush()
    db.execute(
        delete(SandboxVersion).where(
            SandboxVersion.sandbox_id == sandbox.id,
            SandboxVersion.revision <= sandbox.revision - VERSIONS_KEPT,
        )
    )
    return sandbox


def restore_version(db: Session, sandbox_id: int, revision: int, catalog_sha: str | None) -> Sandbox:
    sandbox = _editable(live_sandbox(db, sandbox_id))
    version = db.scalar(
        select(SandboxVersion).where(
            SandboxVersion.sandbox_id == sandbox.id, SandboxVersion.revision == revision
        )
    )
    if version is None:
        raise not_found("Version")
    return save_document(db, sandbox.id, version.document, sandbox.revision, catalog_sha)


def versions(db: Session, sandbox_id: int) -> list[dict[str, Any]]:
    live_sandbox(db, sandbox_id)
    rows = db.scalars(
        select(SandboxVersion)
        .where(SandboxVersion.sandbox_id == sandbox_id)
        .order_by(SandboxVersion.revision.desc())
    )
    return [{"revision": v.revision, "created_at": v.created_at} for v in rows]


def duplicate_sandbox(db: Session, sandbox_id: int) -> Sandbox:
    source = live_sandbox(db, sandbox_id)
    name = free_name(db, source.name, source.folder_id, "sandbox", "copy")
    copy = Sandbox(
        name=name,
        folder_id=source.folder_id,
        description=source.description,
        hotel=source.hotel,
        document=source.document,
        catalog_sha256=source.catalog_sha256,
    )
    db.add(copy)
    db.flush()
    db.add(SandboxVersion(sandbox_id=copy.id, revision=1, document=source.document))
    db.flush()
    return copy


def trash_sandbox(db: Session, sandbox_id: int) -> None:
    sandbox = _editable(live_sandbox(db, sandbox_id))
    sandbox.deleted_at, sandbox.trash_batch, sandbox.trash_root = utcnow(), uuid4().hex, True
    db.flush()


def trash_list(db: Session) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {"kind": "folder", "id": f.id, "name": f.name, "deleted_at": f.deleted_at}
        for f in db.scalars(select(Folder).where(Folder.trash_root.is_(True)))
    ]
    entries += [
        {"kind": "sandbox", "id": s.id, "name": s.name, "deleted_at": s.deleted_at}
        for s in db.scalars(select(Sandbox).where(Sandbox.trash_root.is_(True)))
    ]
    for entry in entries:
        entry["purge_at"] = entry["deleted_at"] + timedelta(days=TRASH_DAYS)
    return sorted(entries, key=lambda e: e["deleted_at"], reverse=True)


def _trashed_root(db: Session, kind: str, item_id: int) -> Folder | Sandbox:
    item = db.get(Folder, item_id) if kind == "folder" else db.get(Sandbox, item_id)
    if item is None or not item.trash_root:
        raise not_found("Trash item")
    return item


def restore(db: Session, kind: str, item_id: int) -> None:
    """Puts back what was trashed together. If the old parent is gone, it returns to the top level."""
    item = _trashed_root(db, kind, item_id)
    batch = item.trash_batch
    if isinstance(item, Folder):
        parent = db.get(Folder, item.parent_id) if item.parent_id else None
        if parent is not None and parent.deleted_at is not None:
            item.parent_id = None
        item.name = free_name(db, item.name, item.parent_id, "folder", "restored")
    else:
        parent = db.get(Folder, item.folder_id) if item.folder_id else None
        if parent is not None and parent.deleted_at is not None:
            item.folder_id = None
        item.name = free_name(db, item.name, item.folder_id, "sandbox", "restored")
    rows = [
        *db.scalars(select(Folder).where(Folder.trash_batch == batch)),
        *db.scalars(select(Sandbox).where(Sandbox.trash_batch == batch)),
    ]
    for row in rows:
        row.deleted_at, row.trash_batch, row.trash_root = None, None, False
    db.flush()


def purge(db: Session, kind: str, item_id: int) -> None:
    # Foreign keys cascade to the contents, including anything trashed separately inside a folder.
    db.delete(_trashed_root(db, kind, item_id))
    db.flush()


def purge_expired(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=TRASH_DAYS)
    removed = 0
    for table in (Folder, Sandbox):
        for row in db.scalars(select(table).where(table.trash_root.is_(True), table.deleted_at < cutoff)):
            db.delete(row)
            removed += 1
    db.flush()
    return removed


def folder_dict(folder: Folder) -> dict[str, Any]:
    return {
        "id": folder.id,
        "parent_id": folder.parent_id,
        "name": folder.name,
        "updated_at": folder.updated_at,
    }


def sandbox_summary(sandbox: Sandbox) -> dict[str, Any]:
    return {
        "id": sandbox.id,
        "folder_id": sandbox.folder_id,
        "name": sandbox.name,
        "description": sandbox.description,
        "kind": sandbox.kind,
        "hotel": sandbox.hotel,
        "revision": sandbox.revision,
        "updated_at": sandbox.updated_at,
    }


def sandbox_full(sandbox: Sandbox) -> dict[str, Any]:
    return {
        **sandbox_summary(sandbox),
        "document": sandbox.document,
        "catalog_sha256": sandbox.catalog_sha256,
    }
