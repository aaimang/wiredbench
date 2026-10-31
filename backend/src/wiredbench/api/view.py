"""What a normal user can see of a room. WIRED config never leaves the server on these routes."""

from __future__ import annotations

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services, viewer
from wiredbench.engine.core import MAX_ADVANCE_MS
from wiredbench.engine.sessions import Run
from wiredbench.errors import ApiError, not_found
from wiredbench.models import Sandbox
from wiredbench.services import preferences
from wiredbench.services import workspace as ws

router = APIRouter(prefix="/api/view", tags=["view"])

# The catalogue can only tell that a box has no offer, so retired or event boxes are hidden with staff ones.
HIDDEN_STAGES = {"not_in_catalogue", "staff", "in_development"}
FURNI_FIELDS = ("id", "classname", "x", "y", "z", "rot", "state")
AVATAR_FIELDS = ("id", "name", "hotel", "figure", "x", "y", "z", "dir", "pose")
ITEM_FIELDS = ("classname", "revision", "xdim", "ydim", "height", "data")
MESSAGES_SHOWN = 20


class ViewInput(BaseModel):
    type: Literal["move", "say", "click", "use"]
    user: int = Field(ge=0, le=2**31)
    x: int | None = Field(None, ge=0, le=64)
    y: int | None = Field(None, ge=0, le=64)
    furni: int | None = Field(None, ge=0, le=2**31)
    text: str | None = Field(None, max_length=500)


class ViewAdvance(BaseModel):
    ms: int = Field(ge=0, le=MAX_ADVANCE_MS)


def _hidden_ids(services: Services, sandbox: Sandbox) -> tuple[set[int], dict[str, dict[str, Any]]]:
    """Returns the furni a normal user must not see, and catalogue details for the rest."""
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    hidden: set[int] = set()
    items: dict[str, dict[str, Any]] = {}
    for furni in document.get("furni", []):
        classname = furni["classname"]
        if classname not in items:
            try:
                items[classname] = services.catalog.item(sandbox.hotel, classname)
            except ApiError:
                items[classname] = {"classname": classname, "release_stage": "unknown"}
        # Unknown boxes are hidden too, because their stage cannot be checked.
        stage = items[classname].get("release_stage")
        if stage in HIDDEN_STAGES or (stage == "unknown" and classname.startswith("wf_")):
            hidden.add(furni["id"])
    return hidden, items


def _public_room(services: Services, sandbox: Sandbox) -> dict[str, Any]:
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    hidden, items = _hidden_ids(services, sandbox)
    furni = [
        {key: item[key] for key in FURNI_FIELDS if key in item}
        for item in document.get("furni", [])
        if item["id"] not in hidden
    ]
    shown = {item["classname"] for item in furni}
    return {
        "id": sandbox.id,
        "name": sandbox.name,
        "hotel": sandbox.hotel,
        "document": {
            "room": document.get("room"),
            "furni": furni,
            "avatars": [
                {key: avatar[key] for key in AVATAR_FIELDS if key in avatar}
                for avatar in document.get("avatars", [])
            ],
        },
        "items": {
            name: {key: details[key] for key in ITEM_FIELDS if key in details}
            for name, details in items.items()
            if name in shown
        },
    }


def _public_state(run: Run, hidden: set[int], user: int | None) -> dict[str, Any]:
    """Only what someone standing in the room could see: no trace, variables, seed or counts."""
    engine = run.engine
    snapshot = engine.snapshot()
    return {
        "now_ms": engine.now_ms,
        "furni": [item for item in snapshot["furni"] if item["id"] not in hidden],
        "users": [{key: u[key] for key in ("id", "name", "x", "y", "dir")} for u in snapshot["users"]],
        "messages": [m for m in engine.messages if m.get("user") == user][-MESSAGES_SHOWN:],
    }


def _sandbox(db: Session, sandbox_id: int) -> Sandbox:
    return ws.live_sandbox(db, sandbox_id)


def _run(sandbox_id: int, services: Services) -> Run:
    run = services.runs.get(sandbox_id)
    if run is None:
        raise ApiError(409, "not_running", "This room is not running.")
    return run


@router.get("/sandboxes")
@viewer
def list_rooms(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Sandbox).where(Sandbox.deleted_at.is_(None)).order_by(Sandbox.name)).all()
    return {"rooms": [{"id": row.id, "name": row.name} for row in rows]}


@router.get("/sandboxes/{sandbox_id}")
@viewer
def get_room(
    sandbox_id: int, services: Services = Depends(get_services), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return _public_room(services, _sandbox(db, sandbox_id))


@router.post("/sandboxes/{sandbox_id}/run", status_code=201)
@viewer
def enter_room(
    sandbox_id: int,
    request: Request,
    user: int | None = Query(None, ge=0, le=2**31),
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Joins the room's run, starting one if needed. An admin's running test is left as it is."""
    sandbox = _sandbox(db, sandbox_id)
    run = services.runs.get(sandbox_id)
    if run is None:
        document = sandbox.document if isinstance(sandbox.document, dict) else {}
        tick_ms = preferences.load(db, services.settings).tick_ms
        run = services.runs.start(sandbox_id, document, secrets.randbelow(2**31), tick_ms)
    audit(db, request, "view_as_enter", sandbox.name)
    db.commit()
    hidden, _ = _hidden_ids(services, sandbox)
    with run.lock:
        return _public_state(run, hidden, user)


@router.post("/sandboxes/{sandbox_id}/run/advance")
@viewer
def advance_room(
    sandbox_id: int,
    body: ViewAdvance,
    user: int | None = Query(None, ge=0, le=2**31),
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sandbox = _sandbox(db, sandbox_id)
    run = _run(sandbox_id, services)
    hidden, _ = _hidden_ids(services, sandbox)
    with run.lock:
        if not run.paused:
            run.engine.advance(body.ms)
        return _public_state(run, hidden, user)


@router.post("/sandboxes/{sandbox_id}/run/input")
@viewer
def room_input(
    sandbox_id: int,
    body: ViewInput,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sandbox = _sandbox(db, sandbox_id)
    run = _run(sandbox_id, services)
    hidden, _ = _hidden_ids(services, sandbox)
    if body.furni is not None and body.furni in hidden:
        raise not_found("Furni")
    with run.lock:
        run.engine.apply_input(body.model_dump(exclude_none=True))
        return _public_state(run, hidden, body.user)
