"""A local copy of Habbo's WIRED Web API, reading and writing a running room.

The room ID is the sandbox ID. Routes are public because they use the API's own keys, sent in headers,
so they carry no cookie and need no CSRF token. Rules marked ASSUMED were not seen on a real room.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services, public
from wiredbench.engine.core import EPOCH_SECONDS, INT64_MAX, INT64_MIN, Engine, Holding
from wiredbench.engine.sessions import Run
from wiredbench.errors import not_found
from wiredbench.models import MockApiKey
from wiredbench.security import hash_token, new_token
from wiredbench.services import workspace as ws

USER_KINDS = {"users": "user", "pets": "pet", "bots": "bot"}
FURNI_KINDS = {
    "furni": "furni",
    "furni-bc": "furni_bc",
    "wall-items": "wall_item",
    "wall-items-bc": "wall_item_bc",
}
MAX_PAGE_SIZE = 100
MAX_BATCH = 50
MAX_ID_DIGITS = 18
ORDERS = ("value", "creation_time", "update_time")

router = APIRouter(prefix="/api/public/rooms/{room_id}", tags=["mock"])
keys_router = APIRouter(prefix="/api/sandboxes/{sandbox_id}/api-keys", tags=["mock"])


class MockError(Exception):
    def __init__(self, status: int, code: str = "") -> None:
        self.status, self.code = status, code


def _not_found() -> MockError:
    return MockError(404, "wired.variables.not_found")


def _entity_not_found() -> MockError:
    return MockError(404, "wired.variables.entity_not_found")


def _invalid_target() -> MockError:
    return MockError(400, "wired.variables.invalid_target")


def _invalid_value() -> MockError:
    return MockError(400, "wired.variables.invalid_value")  # ASSUMED code


def _generic() -> MockError:
    return MockError(404, "not-found")


@dataclass
class Room:
    run: Run
    keys: MockApiKey | None

    @property
    def engine(self) -> Engine:
        return self.run.engine

    def need_read(self, request: Request) -> None:
        self._need(request, "x-wired-read-key", self.keys.read_hash if self.keys else None)

    def need_write(self, request: Request) -> None:
        self._need(request, "x-wired-write-key", self.keys.write_hash if self.keys else None)

    @staticmethod
    def _need(request: Request, header: str, stored: str | None) -> None:
        if stored is None:  # Seen live on a room that has the add-on but no saved keys.
            raise MockError(403, "wired.variables.key_missing")
        if not secrets.compare_digest(hash_token(request.headers.get(header, "")), stored):
            raise MockError(403, "wired.variables.key_invalid")


def get_room(room_id: str, services: Services = Depends(get_services), db: Session = Depends(get_db)) -> Room:
    # Live: a room without the add-on gets the generic 404. Here that is a room that is not running.
    run = None
    if room_id.isdigit() and len(room_id) <= MAX_ID_DIGITS:
        run = services.runs.get(int(room_id))
    if run is None:
        raise _generic()
    return Room(run, db.get(MockApiKey, int(room_id)))


async def json_body(request: Request) -> Any:
    raw = await request.body()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        raise _invalid_value() from None


def _object(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _invalid_value()
    return body


def parse_value(raw: Any) -> int:
    # Live: text and JSON numbers are both accepted, and responses are always text.
    if isinstance(raw, bool) or not isinstance(raw, str | int):
        raise _invalid_value()
    try:
        value = int(raw)
    except ValueError:
        raise _invalid_value() from None
    if not INT64_MIN <= value <= INT64_MAX:
        raise _invalid_value()
    return value


def _time(ms: int) -> str:
    moment = datetime.fromtimestamp(EPOCH_SECONDS, UTC) + timedelta(milliseconds=ms)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _variable(holding: Holding) -> dict[str, str]:
    return {
        "value": str(holding.value),
        "creation_time": _time(holding.created_ms),
        "update_time": _time(holding.updated_ms),
    }


def reply(request: Request, body: Any) -> Response:
    # Live: WIRED GETs send weak ETags and answer 304.
    payload = json.dumps(body, separators=(",", ":")).encode()
    etag = 'W/"' + hashlib.sha256(payload).hexdigest()[:40] + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.method == "GET" and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(payload, media_type="application/json; charset=utf-8", headers=headers)


def error_reply(request: Request, exc: MockError) -> Response:
    # Live: GET errors carry an ETag too. Writes have not been compared, so they stay without one.
    response = reply(request, {"error": exc.code})
    response.status_code = exc.status
    if request.method != "GET":
        del response.headers["etag"]
    return response


def check_target(scope: str, kind: str) -> None:
    # Live: an unknown scope gets an empty 404, and an unknown kind fails before the room is looked at.
    if scope not in ("user", "furni"):
        raise MockError(404)
    if kind not in (USER_KINDS if scope == "user" else FURNI_KINDS):
        raise _invalid_target()


def check_entity(entity: str) -> None:
    # Live: a non-numeric entity gets the router's generic 404, before any key check.
    if not entity.isdigit() or len(entity) > MAX_ID_DIGITS:
        raise _generic()


def target(scope: str = "", kind: str = "") -> None:
    check_target(scope, kind)


def holder(kind: str, entity: str) -> str:
    prefix = {"users": "user", "furni": "furni"}.get(kind, kind)
    return f"{prefix}:{int(entity)}"


def _defined(engine: Engine, scope: str, name: str) -> None:
    if engine.definitions.get(name, {}).get("scope") != scope:
        raise _not_found()


def _holding(engine: Engine, name: str, key: str) -> Holding:
    holding = engine.variables[name].get(key) if name in engine.variables else None
    if holding is None:
        raise _not_found()
    return holding


def _set(engine: Engine, name: str, key: str, value: int) -> Holding:
    # Live: a same-value write still moves update_time. Going through inputs keeps runs replayable.
    engine.apply_input({"type": "api_set", "variable": name, "key": key, "value": value})
    return engine.variables[name][key]


def _delete(engine: Engine, name: str, key: str) -> None:
    engine.apply_input({"type": "api_delete", "variable": name, "key": key})


def _holder_type(scope: str, kind: str) -> str:
    return USER_KINDS[kind] if scope == "user" else FURNI_KINDS[kind]


def _holder_object(engine: Engine, kind: str, entity: str) -> dict[str, Any]:
    number = int(entity)
    if kind == "users":  # The official wrapper needs all three, and a real user always has them.
        user = engine.users.get(number)
        return {
            "id": number,
            "name": user["name"] if user else f"User{number}",
            "unique_id": f"hhus-wb{number}",
        }
    return {"id": number}


def _profile_variables(engine: Engine, key: str) -> dict[str, dict[str, str]]:
    return {name: _variable(store[key]) for name, store in sorted(engine.variables.items()) if key in store}


@router.get("/variables")
@public
def list_definitions(request: Request, room: Room = Depends(get_room)) -> Response:
    room.need_read(request)
    with room.run.lock:
        names: dict[str, list[str]] = {"user": [], "furni": [], "global": []}
        for name, definition in sorted(room.engine.definitions.items()):
            if definition["scope"] in names:
                names[definition["scope"]].append(name)
    return reply(request, {"users": names["user"], "furni": names["furni"], "global": names["global"]})


@router.post("/variables/bulk-delete", status_code=204)
@public
def bulk_delete(request: Request, body: Any = Depends(json_body), room: Room = Depends(get_room)) -> Response:
    room.need_write(request)
    if room.keys is None or not room.keys.allow_mass_deletion:
        raise MockError(403, "wired.variables.key_invalid")  # ASSUMED: the refusal has not been seen live.
    names = _object(body).get("variables")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise _invalid_target()  # ASSUMED code
    with room.run.lock:
        for name in names:
            for key in list(room.engine.variables.get(name, {})):
                _delete(room.engine, name, key)
    return Response(status_code=204)


@router.get("/variables/global/{name}")
@public
def get_global(request: Request, name: str, room: Room = Depends(get_room)) -> Response:
    room.need_read(request)
    with room.run.lock:
        return reply(request, _variable(_holding(room.engine, name, "global")))


@router.patch("/variables/global/{name}")
@public
def patch_global(
    request: Request, name: str, body: Any = Depends(json_body), room: Room = Depends(get_room)
) -> dict[str, str]:
    room.need_write(request)
    with room.run.lock:
        _defined(room.engine, "global", name)
        return _variable(_set(room.engine, name, "global", parse_value(_object(body).get("value"))))


@router.post("/variables/{scope}/{name}/batch")
@public
def batch(
    request: Request,
    scope: str,
    name: str,
    body: Any = Depends(json_body),
    room: Room = Depends(get_room),
) -> dict[str, Any]:
    # Live: a write key alone is refused as missing. A read key alone is ASSUMED to match.
    if not (request.headers.get("x-wired-read-key") and request.headers.get("x-wired-write-key")):
        raise MockError(403, "wired.variables.key_missing")
    room.need_read(request)
    room.need_write(request)
    with room.run.lock:
        _defined(room.engine, scope, name)
        operations = _object(body).get("requests")
        if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_BATCH:
            raise _invalid_target()  # ASSUMED code
        return {"results": [_run_operation(room.engine, scope, name, op) for op in operations]}


def _run_operation(engine: Engine, scope: str, name: str, operation: Any) -> dict[str, Any]:
    op_id = operation.get("op_id") if isinstance(operation, dict) else None
    try:
        operation = _object(operation)
        kind, _, entity = str(operation.get("path", "")).partition("/")
        check_target(scope, kind)
        if not entity.isdigit() or len(entity) > MAX_ID_DIGITS:
            raise _invalid_target()
        key = holder(kind, entity)
        method = operation.get("method")
        value = _object(operation.get("body", {})).get("value")
        if method == "GET":
            result = _variable(_holding(engine, name, key))
        elif method == "PUT":
            result = _variable(_set(engine, name, key, parse_value(value)))
        elif method == "PATCH":
            _holding(engine, name, key)
            result = _variable(_set(engine, name, key, parse_value(value)))
        elif method == "DELETE":
            _holding(engine, name, key)
            _delete(engine, name, key)
            return {"status": 204, "body": None, "error": None, "op_id": op_id}
        else:
            raise _invalid_target()
        # Live: successful operations carry "error": null.
        return {"status": 200, "body": result, "error": None, "op_id": op_id}
    except MockError as exc:
        error = {"code": exc.code, "message": exc.code}
        return {"status": exc.status, "body": None, "error": error, "op_id": op_id}


@router.get("/variables/{scope}/{name}/{kind}/count", dependencies=[Depends(target)])
@public
def count(request: Request, scope: str, name: str, kind: str, room: Room = Depends(get_room)) -> Response:
    room.need_read(request)
    prefix = holder(kind, "0").partition(":")[0] + ":"
    with room.run.lock:
        _defined(room.engine, scope, name)
        total = sum(1 for key in room.engine.variables.get(name, {}) if key.startswith(prefix))
    return reply(request, {"count": total})


@router.get("/variables/{scope}/{name}/{kind}", dependencies=[Depends(target)])
@public
def list_holders(
    request: Request, scope: str, name: str, kind: str, room: Room = Depends(get_room)
) -> Response:
    room.need_read(request)
    query = request.query_params
    try:
        page, size = int(query.get("page", 1)), int(query.get("size", 50))
    except ValueError:
        raise _invalid_target() from None
    # Live: page 0 gives this code, and size is silently limited to 100.
    if page < 1 or size < 1:
        raise _invalid_target()
    size = min(size, MAX_PAGE_SIZE)
    order_by = query.get("order_by") if query.get("order_by") in ORDERS else "value"
    prefix = holder(kind, "0").partition(":")[0] + ":"
    with room.run.lock:
        engine = room.engine
        _defined(engine, scope, name)
        rows = [
            (key, holding)
            for key, holding in engine.variables.get(name, {}).items()
            if key.startswith(prefix)
        ]
        attribute = {"value": "value", "creation_time": "created_ms", "update_time": "updated_ms"}[
            order_by or "value"
        ]
        rows.sort(key=lambda row: getattr(row[1], attribute), reverse=query.get("order_dir", "asc") == "desc")
        items = [
            {
                "variable": _variable(holding),
                _holder_type(scope, kind): _holder_object(engine, kind, key.partition(":")[2]),
            }
            for key, holding in rows[(page - 1) * size : page * size]
        ]
    return reply(request, {"items": items, "page": page, "size": size})


@router.get("/variables/{scope}/{name}/{kind}/{entity}", dependencies=[Depends(target)])
@public
def get_value(
    request: Request, name: str, kind: str, entity: str, room: Room = Depends(get_room)
) -> Response:
    check_entity(entity)
    room.need_read(request)
    with room.run.lock:
        return reply(request, _variable(_holding(room.engine, name, holder(kind, entity))))


@router.put("/variables/{scope}/{name}/{kind}/{entity}", dependencies=[Depends(target)])
@public
def put_value(
    request: Request,
    scope: str,
    name: str,
    kind: str,
    entity: str,
    body: Any = Depends(json_body),
    room: Room = Depends(get_room),
) -> dict[str, str]:
    check_entity(entity)
    room.need_write(request)
    with room.run.lock:
        _defined(room.engine, scope, name)
        value = parse_value(_object(body).get("value"))
        return _variable(_set(room.engine, name, holder(kind, entity), value))


@router.patch("/variables/{scope}/{name}/{kind}/{entity}", dependencies=[Depends(target)])
@public
def patch_value(
    request: Request,
    name: str,
    kind: str,
    entity: str,
    body: Any = Depends(json_body),
    room: Room = Depends(get_room),
) -> dict[str, str]:
    check_entity(entity)
    room.need_write(request)
    with room.run.lock:
        key = holder(kind, entity)
        _holding(room.engine, name, key)
        return _variable(_set(room.engine, name, key, parse_value(_object(body).get("value"))))


@router.delete("/variables/{scope}/{name}/{kind}/{entity}", status_code=204, dependencies=[Depends(target)])
@public
def delete_value(
    request: Request, name: str, kind: str, entity: str, room: Room = Depends(get_room)
) -> Response:
    check_entity(entity)
    room.need_write(request)
    with room.run.lock:
        key = holder(kind, entity)
        _holding(room.engine, name, key)
        _delete(room.engine, name, key)
    return Response(status_code=204)


def _profile(engine: Engine, scope: str, kind: str, entity: str) -> dict[str, Any]:
    variables = _profile_variables(engine, holder(kind, entity))
    if not variables:  # Live: a profile exists only while the holder has a variable.
        raise _entity_not_found()
    return {_holder_type(scope, kind): _holder_object(engine, kind, entity), "variables": variables}


@router.get("/variables_profile/global")
@public
def get_global_profile(request: Request, room: Room = Depends(get_room)) -> Response:
    room.need_read(request)
    with room.run.lock:
        return reply(request, {"variables": _profile_variables(room.engine, "global")})


@router.patch("/variables_profile/global")
@public
def patch_global_profile(
    request: Request, body: Any = Depends(json_body), room: Room = Depends(get_room)
) -> dict[str, Any]:
    room.need_write(request)
    with room.run.lock:
        for name, raw in _changes(body).items():
            _defined(room.engine, "global", name)
            _set(room.engine, name, "global", parse_value(raw))
        return {"variables": _profile_variables(room.engine, "global")}


def _changes(body: Any) -> dict[str, Any]:
    changes = _object(body).get("variables", {})
    if not isinstance(changes, dict):
        raise _invalid_value()
    return changes


@router.get("/variables_profile/user/users")
@public
def lookup_profile(request: Request, room: Room = Depends(get_room)) -> Response:
    room.need_read(request)
    name, unique_id = request.query_params.get("name"), request.query_params.get("unique_id")
    with room.run.lock:
        engine = room.engine
        for number, user in engine.users.items():
            if (name and user["name"].lower() == name.lower()) or unique_id == f"hhus-wb{number}":
                return reply(request, _profile(engine, "user", "users", str(number)))
    raise _entity_not_found()


def _profile_target(scope: str, kind: str, entity: str) -> None:
    check_target(scope, kind)
    check_entity(entity)


def _read_profile(request: Request, scope: str, kind: str, entity: str, room: Room) -> Response:
    _profile_target(scope, kind, entity)
    room.need_read(request)
    with room.run.lock:
        return reply(request, _profile(room.engine, scope, kind, entity))


def _patch_profile(
    request: Request, scope: str, kind: str, entity: str, body: Any, room: Room
) -> dict[str, Any]:
    _profile_target(scope, kind, entity)
    room.need_write(request)
    with room.run.lock:
        engine = room.engine
        _profile(engine, scope, kind, entity)
        key = holder(kind, entity)
        for name, raw in _changes(body).items():
            if raw is None:
                if key in engine.variables.get(name, {}):
                    _delete(engine, name, key)
            else:
                _defined(engine, scope, name)
                _set(engine, name, key, parse_value(raw))
        variables = _profile_variables(engine, key)
        return {_holder_type(scope, kind): _holder_object(engine, kind, entity), "variables": variables}


@router.get("/variables_profile/user/{kind}/{entity}")
@public
def get_user_profile(request: Request, kind: str, entity: str, room: Room = Depends(get_room)) -> Response:
    return _read_profile(request, "user", kind, entity, room)


@router.patch("/variables_profile/user/{kind}/{entity}")
@public
def patch_user_profile(
    request: Request, kind: str, entity: str, body: Any = Depends(json_body), room: Room = Depends(get_room)
) -> dict[str, Any]:
    return _patch_profile(request, "user", kind, entity, body, room)


@router.delete("/variables_profile/user/{kind}/{entity}", status_code=204)
@public
def delete_user_profile(request: Request, kind: str, entity: str, room: Room = Depends(get_room)) -> Response:
    _profile_target("user", kind, entity)
    room.need_write(request)
    with room.run.lock:
        engine = room.engine
        _profile(engine, "user", kind, entity)
        key = holder(kind, entity)
        for name, store in list(engine.variables.items()):
            if key in store:
                _delete(engine, name, key)
    return Response(status_code=204)


@router.get("/variables_profile/furni/{kind}/{entity}")
@public
def get_furni_profile(request: Request, kind: str, entity: str, room: Room = Depends(get_room)) -> Response:
    return _read_profile(request, "furni", kind, entity, room)


@router.patch("/variables_profile/furni/{kind}/{entity}")
@public
def patch_furni_profile(
    request: Request, kind: str, entity: str, body: Any = Depends(json_body), room: Room = Depends(get_room)
) -> dict[str, Any]:
    return _patch_profile(request, "furni", kind, entity, body, room)


# --- Managing a sandbox's keys, which needs the admin login ---


class KeyOptions(BaseModel):
    allow_mass_deletion: bool = False


def _key_status(row: MockApiKey | None) -> dict[str, Any]:
    return {
        "configured": row is not None,
        "allow_mass_deletion": bool(row and row.allow_mass_deletion),
        "created_at": row.created_at if row else None,
    }


@keys_router.get("")
def key_status(sandbox_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    ws.live_sandbox(db, sandbox_id)
    return _key_status(db.get(MockApiKey, sandbox_id))


@keys_router.post("", status_code=201)
def generate_keys(
    sandbox_id: int, body: KeyOptions, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Replaces any existing keys. This is the only time the keys can be read."""
    sandbox = ws.live_sandbox(db, sandbox_id)
    read_key, write_key = new_token(), new_token()
    row = db.get(MockApiKey, sandbox_id)
    if row is None:
        row = MockApiKey(sandbox_id=sandbox_id, read_hash="", write_hash="")
        db.add(row)
    row.read_hash, row.write_hash = hash_token(read_key), hash_token(write_key)
    row.allow_mass_deletion = body.allow_mass_deletion
    audit(db, request, "mock_keys_generate", sandbox.name)
    db.commit()
    return {**_key_status(row), "read_key": read_key, "write_key": write_key}


@keys_router.delete("", status_code=204)
def clear_keys(sandbox_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    sandbox = ws.live_sandbox(db, sandbox_id)
    row = db.get(MockApiKey, sandbox_id)
    if row is None:
        raise not_found("API key")
    db.delete(row)
    audit(db, request, "mock_keys_clear", sandbox.name)
    db.commit()
