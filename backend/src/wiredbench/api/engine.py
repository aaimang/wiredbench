from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services, ticker
from wiredbench.config import Hotel
from wiredbench.engine import box_facts, coverage, internal
from wiredbench.engine.boxes import BOXES, catalogue, is_box
from wiredbench.engine.checker import check_room
from wiredbench.engine.core import MAX_ADVANCE_MS
from wiredbench.engine.guide import GUIDE
from wiredbench.engine.sessions import Run, run_command, state
from wiredbench.engine.tutorials import TUTORIALS
from wiredbench.errors import ApiError, not_found
from wiredbench.models import Sandbox
from wiredbench.services import preferences
from wiredbench.services import workspace as ws

router = APIRouter(prefix="/api", tags=["engine"])

GUIDE_PAGE = 200
Int = Annotated[int, Field(ge=0, le=2**31)]


class StartRun(BaseModel):
    seed: Int | None = None


class Advance(BaseModel):
    ms: int = Field(ge=0, le=MAX_ADVANCE_MS)


class Input(BaseModel):
    type: Literal[
        "move",
        "turn",
        "say",
        "click",
        "use",
        "enter",
        "leave",
        "game_start",
        "game_end",
        "box_settings",
        "set_value",
        "user_detail",
    ]
    user: Int | None = None
    x: int | None = Field(None, ge=0, le=64)
    y: int | None = Field(None, ge=0, le=64)
    dir: int | None = Field(None, ge=0, le=7)
    furni: Int | None = None
    text: str | None = Field(None, max_length=500)
    settings: dict[str, Any] | None = None
    detail: str | None = Field(None, max_length=32)
    amount: int | None = None
    variable: str | None = Field(None, max_length=64)
    key: str | None = Field(None, max_length=64)
    # A string, because 64-bit values do not survive being a JavaScript number.
    value: str | None = Field(None, pattern=r"^-?\d{1,19}$")


class Command(BaseModel):
    text: str = Field(max_length=200)


class Tutorial(BaseModel):
    hotel: Hotel | None = None


def furni_states(services: Services, sandbox: Sandbox) -> dict[str, list[int]]:
    """How many states each furni in a room really has, read from art that is already downloaded."""
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    found: dict[str, list[int]] = {}
    for classname in {item["classname"] for item in document.get("furni", [])}:
        try:
            revision = services.catalog.item(sandbox.hotel, classname)["revision"]
        except ApiError:
            continue
        if states := services.assets.cached_states(revision, classname):
            found[classname] = states
    return found


def not_standable(services: Services, sandbox: Sandbox) -> set[str]:
    """Furni in a room that the catalogue says nobody can stand or sit on."""
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    found: set[str] = set()
    for classname in {item["classname"] for item in document.get("furni", [])}:
        try:
            data = services.catalog.item(sandbox.hotel, classname).get("data") or {}
        except ApiError:
            continue
        if data.get("canstandon") is False and data.get("cansiton") is not True:
            found.add(classname)
    return found


def furni_facts(services: Services, sandbox: Sandbox) -> dict[str, dict[str, Any]]:
    """What the catalogue says about each furni in a room, for its built-in variables."""
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    found: dict[str, dict[str, Any]] = {}
    for classname in {item["classname"] for item in document.get("furni", [])}:
        try:
            item = services.catalog.item(sandbox.hotel, classname)
        except ApiError:
            continue
        data = item.get("data") or {}
        found[classname] = {
            "height": item.get("height") or 0,
            "xdim": item.get("xdim") or 1,
            "ydim": item.get("ydim") or 1,
            "can_stand": bool(data.get("canstandon")),
            "can_sit": bool(data.get("cansiton")),
            "can_lay": bool(data.get("canlayon")),
        }
    return found


def _run(sandbox_id: int, services: Services) -> Run:
    run = services.runs.get(sandbox_id)
    if run is None:
        raise ApiError(409, "not_running", "This room is not running. Press Run first.")
    return run


@router.get("/engine/built-in-variables")
def built_in_variables() -> list[dict[str, Any]]:
    return internal.rows()


@router.get("/engine/boxes")
def boxes() -> dict[str, Any]:
    checked = coverage.load()["boxes"]
    return {
        name: {**spec, "checked_on": checked.get(name, {}).get("room")} for name, spec in catalogue().items()
    }


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
    run = services.runs.start(
        sandbox_id,
        document,
        seed,
        tick_ms,
        furni_states(services, sandbox),
        not_standable(services, sandbox),
        furni_facts(services, sandbox),
    )
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
@ticker
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


@router.get("/sandboxes/{sandbox_id}/run/built-ins")
def run_built_ins(
    sandbox_id: int,
    target: Literal["furni", "user", "global"] = Query("global"),
    holder: Int | None = None,
    services: Services = Depends(get_services),
) -> list[dict[str, Any]]:
    run = _run(sandbox_id, services)
    with run.lock:
        return run.engine.view_built_ins(target, holder)


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


@router.get("/sandboxes/{sandbox_id}/check")
def check_sandbox(sandbox_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    sandbox = ws.live_sandbox(db, sandbox_id)
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    return {"issues": check_room(document)}


@router.get("/tutorials")
def list_tutorials() -> list[dict[str, str]]:
    return [
        {"slug": slug, "title": item["title"], "description": item["description"], "try": item["try"]}
        for slug, item in TUTORIALS.items()
    ]


@router.get("/guide")
def guide(
    hotel: Hotel | None = None,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Every WIRED box the catalogue or the engine knows, and how far its behaviour can be trusted."""
    chosen = hotel or preferences.load(db, services.settings).default_hotel
    listed: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        page = services.catalog.search(chosen, scope="wired", offset=offset, limit=GUIDE_PAGE)
        listed.update({item["classname"]: item for item in page["items"]})
        offset += GUIDE_PAGE
        if len(page["items"]) < GUIDE_PAGE:
            break
    rows = []
    tracked = {row["classname"]: row for row in coverage.rows()}
    checked = coverage.room_checked()
    for classname in sorted(listed | dict.fromkeys(BOXES, {})):
        item, spec, fact = listed.get(classname, {}), BOXES.get(classname), box_facts.of(classname)
        purpose, example = GUIDE.get(classname, (item.get("description") or "", ""))
        evidence = tracked.get(classname)
        if classname in checked:
            status = "real_room"
        elif spec:
            status = spec["fidelity"]
        else:
            status = "not_simulated" if is_box(classname) else "other_furni"
        rows.append(
            {
                "classname": classname,
                "name": item.get("name") or classname,
                "type": item.get("wired_type")
                or (spec["kind"] if spec else (fact or {}).get("section", "utility")),
                "purpose": purpose,
                "example": example,
                "status": status,
                "release_stage": item.get("release_stage", "unknown"),
                "revision": item.get("revision"),
                # A box the tracker has never seen is new to Habbo since the last check.
                "evidence": evidence["evidence"] if evidence else "new",
                "room_checked_on": evidence["room_checked_on"] if evidence else None,
                "options_mapped": bool(evidence and evidence["options_mapped"]),
                "default_numbers": fact["numbers"] if fact else None,
            }
        )
    return {"hotel": chosen, "rows": rows, "coverage": coverage.summary()}


@router.post("/tutorials/{slug}", status_code=201)
def add_tutorial(
    slug: str,
    body: Tutorial,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    tutorial = TUTORIALS.get(slug)
    if tutorial is None:
        raise not_found("Tutorial")
    hotel = body.hotel or preferences.load(db, services.settings).default_hotel
    name = ws.free_name(db, tutorial["title"], None, "sandbox", "copy")
    sandbox = ws.create_sandbox(db, name, None, tutorial["description"], hotel, None)
    ws.save_document(
        db, sandbox.id, tutorial["build"](hotel), sandbox.revision, services.catalog.current_sha(hotel)
    )
    audit(db, request, "tutorial_add", name)
    db.commit()
    return ws.sandbox_full(sandbox)
