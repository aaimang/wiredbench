from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services
from wiredbench.config import Hotel
from wiredbench.engine.boxes import catalogue
from wiredbench.engine.core import MAX_ADVANCE_MS
from wiredbench.engine.sessions import Run, run_command, state
from wiredbench.engine.tutorials import time_tracking
from wiredbench.errors import ApiError
from wiredbench.models import Sandbox
from wiredbench.services import preferences
from wiredbench.services import workspace as ws

router = APIRouter(prefix="/api", tags=["engine"])

Int = Annotated[int, Field(ge=0, le=2**31)]


class StartRun(BaseModel):
    seed: Int | None = None


class Advance(BaseModel):
    ms: int = Field(ge=0, le=MAX_ADVANCE_MS)


class Input(BaseModel):
    type: Literal["move", "say", "click", "use", "enter", "leave"]
    user: Int | None = None
    x: int | None = Field(None, ge=0, le=64)
    y: int | None = Field(None, ge=0, le=64)
    furni: Int | None = None
    text: str | None = Field(None, max_length=500)


class Command(BaseModel):
    text: str = Field(max_length=200)


class Tutorial(BaseModel):
    hotel: Hotel | None = None


def _run(sandbox_id: int, services: Services) -> Run:
    run = services.runs.get(sandbox_id)
    if run is None:
        raise ApiError(409, "not_running", "This room is not running. Press Run first.")
    return run


@router.get("/engine/boxes")
def boxes() -> dict[str, Any]:
    return catalogue()


@router.post("/sandboxes/{sandbox_id}/run", status_code=201)
def start_run(
    sandbox_id: int,
    body: StartRun,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sandbox = ws.live_sandbox(db, sandbox_id)
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    tick_ms = preferences.load(db, services.settings).tick_ms
    run = services.runs.start(sandbox_id, document, seed, tick_ms)
    audit(db, request, "run_start", sandbox.name)
    db.commit()
    return state(run, 0)


@router.get("/sandboxes/{sandbox_id}/run")
def get_run(
    sandbox_id: int, since: int = Query(0, ge=0), services: Services = Depends(get_services)
) -> dict[str, Any]:
    run = _run(sandbox_id, services)
    with run.lock:
        return state(run, since)


@router.post("/sandboxes/{sandbox_id}/run/advance")
def advance(
    sandbox_id: int,
    body: Advance,
    since: int = Query(0, ge=0),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    run = _run(sandbox_id, services)
    with run.lock:
        if not run.paused:
            run.engine.advance(body.ms)
        return state(run, since)


@router.post("/sandboxes/{sandbox_id}/run/input")
def send_input(
    sandbox_id: int,
    body: Input,
    since: int = Query(0, ge=0),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    run = _run(sandbox_id, services)
    with run.lock:
        entry = body.model_dump(exclude_none=True)
        if "user" not in entry and run.acting_as is not None:
            entry["user"] = run.acting_as
        run.engine.apply_input(entry)
        return state(run, since)


@router.post("/sandboxes/{sandbox_id}/run/command")
def command(
    sandbox_id: int,
    body: Command,
    since: int = Query(0, ge=0),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    run = _run(sandbox_id, services)
    with run.lock:
        answer = run_command(run, body.text)
        return {**state(run, since), "answer": answer}


@router.delete("/sandboxes/{sandbox_id}/run", status_code=204)
def stop_run(sandbox_id: int, services: Services = Depends(get_services)) -> None:
    services.runs.stop(sandbox_id)


@router.get("/dashboard")
def dashboard(services: Services = Depends(get_services), db: Session = Depends(get_db)) -> dict[str, Any]:
    rooms = []
    for sandbox_id, run in services.runs.running():
        sandbox = db.get(Sandbox, sandbox_id)
        if sandbox is None or sandbox.deleted_at is not None:
            continue
        with run.lock:
            rooms.append(
                {"id": sandbox_id, "name": sandbox.name, "paused": run.paused, **run.engine.dashboard()}
            )
    return {"rooms": rooms}


@router.post("/tutorials/time-tracking", status_code=201)
def add_time_tracking(
    body: Tutorial,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    hotel = body.hotel or preferences.load(db, services.settings).default_hotel
    name = ws.free_name(db, "Time tracking example", None, "sandbox", "copy")
    sandbox = ws.create_sandbox(
        db, name, None, "From baikal's Habbo Wired time tracking article.", hotel, None
    )
    ws.save_document(
        db, sandbox.id, time_tracking(hotel), sandbox.revision, services.catalog.current_sha(hotel)
    )
    audit(db, request, "tutorial_add", name)
    db.commit()
    return ws.sandbox_full(sandbox)
