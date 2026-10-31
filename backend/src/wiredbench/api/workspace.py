from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services
from wiredbench.config import Hotel
from wiredbench.errors import ApiError
from wiredbench.models import Sandbox
from wiredbench.services import preferences, room
from wiredbench.services import workspace as ws

router = APIRouter(prefix="/api", tags=["workspace"])

MAX_DOCUMENT_BYTES = 1_500_000
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a name.")
    if CONTROL.search(value):
        raise ValueError("Names cannot contain control characters.")
    return value


Name = Annotated[str, Field(max_length=120), AfterValidator(_clean_name)]


class FolderCreate(BaseModel):
    name: Name
    parent_id: int | None = None


class FolderUpdate(BaseModel):
    name: Name | None = None
    parent_id: int | None = None


class SandboxCreate(BaseModel):
    name: Name
    folder_id: int | None = None
    description: str = Field("", max_length=2000)
    hotel: Hotel | None = None


class SandboxUpdate(BaseModel):
    name: Name | None = None
    folder_id: int | None = None
    description: str | None = Field(None, max_length=2000)


class DocumentSave(BaseModel):
    document: dict[str, Any]
    base_revision: int = Field(ge=1)


def _changes(body: BaseModel) -> dict[str, Any]:
    """Only the fields sent, so moving to the top level (null) differs from not moving at all."""
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "description"):
        if changes.get(required, "") is None:
            del changes[required]
    return changes


@router.get("/workspace/tree")
def tree(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ws.tree(db)


@router.post("/folders", status_code=201)
def create_folder(body: FolderCreate, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    folder = ws.create_folder(db, body.name, body.parent_id)
    audit(db, request, "folder_create", folder.name)
    db.commit()
    return ws.folder_dict(folder)


@router.patch("/folders/{folder_id}")
def update_folder(
    folder_id: int, body: FolderUpdate, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    folder = ws.update_folder(db, folder_id, _changes(body))
    audit(db, request, "folder_update", folder.name)
    db.commit()
    return ws.folder_dict(folder)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    ws.trash_folder(db, folder_id)
    audit(db, request, "folder_trash", str(folder_id))
    db.commit()


@router.post("/sandboxes", status_code=201)
def create_sandbox(
    body: SandboxCreate,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    hotel = body.hotel or preferences.load(db, services.settings).default_hotel
    sandbox = ws.create_sandbox(
        db, body.name, body.folder_id, body.description, hotel, services.catalog.current_sha(hotel)
    )
    audit(db, request, "sandbox_create", sandbox.name)
    db.commit()
    return ws.sandbox_full(sandbox)


@router.get("/sandboxes/{sandbox_id}")
def get_sandbox(sandbox_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ws.sandbox_full(ws.live_sandbox(db, sandbox_id))


@router.patch("/sandboxes/{sandbox_id}")
def update_sandbox(
    sandbox_id: int, body: SandboxUpdate, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    sandbox = ws.update_sandbox(db, sandbox_id, _changes(body))
    audit(db, request, "sandbox_update", sandbox.name)
    db.commit()
    return ws.sandbox_full(sandbox)


@router.put("/sandboxes/{sandbox_id}/document")
def save_document(
    sandbox_id: int,
    body: DocumentSave,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if len(json.dumps(body.document)) > MAX_DOCUMENT_BYTES:
        raise ApiError(413, "document_too_large", "This sandbox is too large to save.")
    room.validate(body.document)
    sandbox: Sandbox = ws.live_sandbox(db, sandbox_id)
    saved = ws.save_document(
        db, sandbox_id, body.document, body.base_revision, services.catalog.current_sha(sandbox.hotel)
    )
    audit(db, request, "sandbox_save", f"{saved.name} r{saved.revision}")
    db.commit()
    return ws.sandbox_full(saved)


@router.post("/sandboxes/{sandbox_id}/duplicate", status_code=201)
def duplicate_sandbox(sandbox_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    copy = ws.duplicate_sandbox(db, sandbox_id)
    audit(db, request, "sandbox_duplicate", copy.name)
    db.commit()
    return ws.sandbox_full(copy)


@router.delete("/sandboxes/{sandbox_id}", status_code=204)
def delete_sandbox(sandbox_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    ws.trash_sandbox(db, sandbox_id)
    audit(db, request, "sandbox_trash", str(sandbox_id))
    db.commit()


@router.get("/sandboxes/{sandbox_id}/versions")
def versions(sandbox_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return ws.versions(db, sandbox_id)


@router.post("/sandboxes/{sandbox_id}/versions/{revision}/restore")
def restore_version(
    sandbox_id: int,
    revision: int,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sandbox = ws.live_sandbox(db, sandbox_id)
    restored = ws.restore_version(db, sandbox_id, revision, services.catalog.current_sha(sandbox.hotel))
    audit(db, request, "sandbox_restore_version", f"{restored.name} r{revision}")
    db.commit()
    return ws.sandbox_full(restored)


@router.get("/trash")
def trash(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return ws.trash_list(db)


@router.post("/trash/{kind}/{item_id}/restore", status_code=204)
def restore(
    kind: Literal["folder", "sandbox"], item_id: int, request: Request, db: Session = Depends(get_db)
) -> None:
    ws.restore(db, kind, item_id)
    audit(db, request, "trash_restore", f"{kind} {item_id}")
    db.commit()


@router.delete("/trash/{kind}/{item_id}", status_code=204)
def purge(
    kind: Literal["folder", "sandbox"], item_id: int, request: Request, db: Session = Depends(get_db)
) -> None:
    ws.purge(db, kind, item_id)
    audit(db, request, "trash_purge", f"{kind} {item_id}")
    db.commit()
