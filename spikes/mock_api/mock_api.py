"""Spike: an in-memory mock of the Habbo WIRED Web API, matching observed live behaviour.

Rules marked ASSUMED were not observed on a real room and need checking with real keys.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

USER_KINDS = {"users": "user", "pets": "pet", "bots": "bot"}
FURNI_KINDS = {"furni": "furni", "furni-bc": "furni_bc", "wall-items": "wall_item", "wall-items-bc": "wall_item_bc"}
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
MAX_PAGE_SIZE = 100
MAX_BATCH = 50


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


NOT_FOUND = ApiError(404, "wired.variables.not_found")
ENTITY_NOT_FOUND = ApiError(404, "wired.variables.entity_not_found")
INVALID_TARGET = ApiError(400, "wired.variables.invalid_target")
KEY_INVALID = ApiError(403, "wired.variables.key_invalid")
KEY_MISSING = ApiError(403, "wired.variables.key_missing")
GENERIC_NOT_FOUND = ApiError(404, "not-found")


@dataclass
class Room:
    read_key: str
    write_key: str
    allow_mass_deletion: bool = False
    definitions: dict[str, set[str]] = field(default_factory=lambda: {"user": set(), "furni": set(), "global": set()})
    # (scope, kind, entity id) -> name -> stored variable. Global uses ("global", "", "").
    values: dict[tuple[str, str, str], dict[str, dict]] = field(default_factory=dict)
    users: dict[str, dict] = field(default_factory=dict)

    def holder(self, scope: str, kind: str, entity: str) -> dict[str, dict]:
        return self.values.setdefault((scope, kind, entity), {})


def parse_value(raw) -> str:
    # Live: strings and JSON numbers are both accepted; responses are always strings.
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise ApiError(400, "wired.variables.invalid_value")  # ASSUMED code
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "wired.variables.invalid_value") from None  # ASSUMED code
    if not INT64_MIN <= value <= INT64_MAX:
        raise ApiError(400, "wired.variables.invalid_value")  # ASSUMED code
    return str(value)


def set_value(store: dict[str, dict], name: str, value: str) -> dict:
    timestamp = now()
    current = store.get(name)
    if current is None:
        current = {"value": value, "creation_time": timestamp, "update_time": timestamp}
        store[name] = current
    else:
        # Live: a same-value write still bumps update_time.
        current["value"], current["update_time"] = value, timestamp
    return current


def check_target(scope: str, kind: str) -> None:
    if scope not in ("user", "furni"):
        raise INVALID_TARGET
    if kind not in (USER_KINDS if scope == "user" else FURNI_KINDS):
        raise INVALID_TARGET


def check_entity(entity: str) -> None:
    # Live: a non-numeric entity id gets the router's generic 404.
    if not entity.isdigit():
        raise GENERIC_NOT_FOUND


def holder_object(room: Room, scope: str, kind: str, entity: str) -> dict:
    if scope == "user" and kind == "users":
        return room.users.get(entity, {"id": int(entity)})
    return {"id": int(entity)}


def holder_key(scope: str, kind: str) -> str:
    return USER_KINDS[kind] if scope == "user" else FURNI_KINDS[kind]


def create_app(rooms: dict[int, Room]) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    def room_of(room_id: str) -> Room:
        # Live: a room without the add-on, or that does not exist, gives the generic 404.
        room = rooms.get(int(room_id)) if room_id.isdigit() else None
        if room is None:
            raise GENERIC_NOT_FOUND
        return room

    def need_read(request: Request, room: Room) -> None:
        if not secrets.compare_digest(request.headers.get("x-wired-read-key", ""), room.read_key):
            raise KEY_INVALID

    def need_write(request: Request, room: Room) -> None:
        if not secrets.compare_digest(request.headers.get("x-wired-write-key", ""), room.write_key):
            raise KEY_INVALID

    def reply(request: Request, body) -> Response:
        # Live: WIRED GETs send weak ETags and answer 304.
        payload = json.dumps(body, separators=(",", ":")).encode()
        etag = 'W/"' + hashlib.sha1(payload).hexdigest() + '"'
        if request.method == "GET" and request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"etag": etag})
        return Response(payload, media_type="application/json; charset=utf-8", headers={"etag": etag})

    def definition(room: Room, scope: str, name: str) -> None:
        if name not in room.definitions.get(scope, ()):
            raise NOT_FOUND

    prefix = "/api/public/rooms/{room_id}"

    @app.get(prefix + "/variables")
    async def list_definitions(request: Request, room_id: str):
        room = room_of(room_id)
        need_read(request, room)
        return reply(request, {
            "users": sorted(room.definitions["user"]),
            "furni": sorted(room.definitions["furni"]),
            "global": sorted(room.definitions["global"]),
        })

    @app.post(prefix + "/variables/bulk-delete")
    async def bulk_delete(request: Request, room_id: str):
        room = room_of(room_id)
        need_write(request, room)
        if not room.allow_mass_deletion:
            raise KEY_INVALID  # ASSUMED: refusal was never observed live.
        names = (await request.json()).get("variables")
        if not isinstance(names, list):
            raise INVALID_TARGET  # ASSUMED code
        for store in room.values.values():
            for name in names:
                store.pop(name, None)
        return Response(status_code=204)

    @app.get(prefix + "/variables/global/{name}")
    async def get_global(request: Request, room_id: str, name: str):
        room = room_of(room_id)
        need_read(request, room)
        store = room.holder("global", "", "")
        if name not in store:
            raise NOT_FOUND
        return reply(request, store[name])

    @app.patch(prefix + "/variables/global/{name}")
    async def patch_global(request: Request, room_id: str, name: str):
        room = room_of(room_id)
        need_write(request, room)
        definition(room, "global", name)
        return set_value(room.holder("global", "", ""), name, parse_value((await request.json()).get("value")))

    @app.post(prefix + "/variables/{scope}/{name}/batch")
    async def batch(request: Request, room_id: str, scope: str, name: str):
        room = room_of(room_id)
        has_read = "x-wired-read-key" in request.headers
        has_write = "x-wired-write-key" in request.headers
        if has_read != has_write:
            raise KEY_MISSING  # Live for write-only. ASSUMED for read-only.
        need_read(request, room)
        need_write(request, room)
        definition(room, scope, name)
        ops = (await request.json()).get("requests")
        if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_BATCH:
            raise INVALID_TARGET  # ASSUMED code
        return {"results": [_run_op(room, scope, name, op) for op in ops]}

    @app.get(prefix + "/variables/{scope}/{name}/{kind}/count")
    async def count(request: Request, room_id: str, scope: str, name: str, kind: str):
        room = room_of(room_id)
        need_read(request, room)
        check_target(scope, kind)
        definition(room, scope, name)
        total = sum(1 for (s, k, _), store in room.values.items() if s == scope and k == kind and name in store)
        return reply(request, {"count": total})

    @app.get(prefix + "/variables/{scope}/{name}/{kind}")
    async def list_holders(request: Request, room_id: str, scope: str, name: str, kind: str):
        room = room_of(room_id)
        need_read(request, room)
        check_target(scope, kind)
        definition(room, scope, name)
        query = request.query_params
        order_by = query.get("order_by", "value")
        descending = query.get("order_dir", "asc") == "desc"
        try:
            page, size = int(query.get("page", 1)), int(query.get("size", 50))
        except ValueError:
            raise INVALID_TARGET from None
        # Live: page 0 gives this code, and size is silently clamped to 100.
        if page < 1 or size < 1:
            raise INVALID_TARGET
        size = min(size, MAX_PAGE_SIZE)
        rows = [(e, st[name]) for (s, k, e), st in room.values.items() if s == scope and k == kind and name in st]
        key = (lambda r: int(r[1]["value"])) if order_by == "value" else (lambda r: r[1].get(order_by, ""))
        rows.sort(key=key, reverse=descending)
        chosen = rows[(page - 1) * size : page * size]
        items = [{"variable": v, holder_key(scope, kind): holder_object(room, scope, kind, e)} for e, v in chosen]
        return reply(request, {"items": items, "page": page, "size": size})

    @app.get(prefix + "/variables/{scope}/{name}/{kind}/{entity}")
    async def get_value(request: Request, room_id: str, scope: str, name: str, kind: str, entity: str):
        room = room_of(room_id)
        need_read(request, room)
        check_target(scope, kind)
        check_entity(entity)
        store = room.holder(scope, kind, entity)
        if name not in store:
            raise NOT_FOUND
        return reply(request, store[name])

    @app.put(prefix + "/variables/{scope}/{name}/{kind}/{entity}")
    async def put_value(request: Request, room_id: str, scope: str, name: str, kind: str, entity: str):
        room = room_of(room_id)
        need_write(request, room)
        check_target(scope, kind)
        check_entity(entity)
        definition(room, scope, name)
        return set_value(room.holder(scope, kind, entity), name, parse_value((await request.json()).get("value")))

    @app.patch(prefix + "/variables/{scope}/{name}/{kind}/{entity}")
    async def patch_value(request: Request, room_id: str, scope: str, name: str, kind: str, entity: str):
        room = room_of(room_id)
        need_write(request, room)
        check_target(scope, kind)
        check_entity(entity)
        store = room.holder(scope, kind, entity)
        if name not in store:
            raise NOT_FOUND
        return set_value(store, name, parse_value((await request.json()).get("value")))

    @app.delete(prefix + "/variables/{scope}/{name}/{kind}/{entity}")
    async def delete_value(request: Request, room_id: str, scope: str, name: str, kind: str, entity: str):
        room = room_of(room_id)
        need_write(request, room)
        check_target(scope, kind)
        check_entity(entity)
        store = room.holder(scope, kind, entity)
        if store.pop(name, None) is None:
            raise NOT_FOUND
        return Response(status_code=204)

    def user_profile(room: Room, entity: str) -> dict:
        store = room.values.get(("user", "users", entity))
        if not store:  # Live: a profile exists only while the user holds a variable.
            raise ENTITY_NOT_FOUND
        return {"user": room.users.get(entity, {"id": int(entity)}), "variables": store}

    @app.get(prefix + "/variables_profile/user/users")
    async def profile_lookup(request: Request, room_id: str):
        room = room_of(room_id)
        need_read(request, room)
        name, unique_id = request.query_params.get("name"), request.query_params.get("unique_id")
        for entity, user in room.users.items():
            if (name and user.get("name", "").lower() == name.lower()) or (unique_id and user.get("unique_id") == unique_id):
                return reply(request, user_profile(room, entity))
        raise ENTITY_NOT_FOUND

    def any_profile(room: Room, scope: str, kind: str, entity: str) -> dict:
        check_target(scope, kind)
        check_entity(entity)
        store = room.values.get((scope, kind, entity))
        if not store:
            raise ENTITY_NOT_FOUND
        return {holder_key(scope, kind): holder_object(room, scope, kind, entity), "variables": store}

    @app.get(prefix + "/variables_profile/global")
    async def get_global_profile(request: Request, room_id: str):
        room = room_of(room_id)
        need_read(request, room)
        return reply(request, {"variables": room.holder("global", "", "")})

    @app.patch(prefix + "/variables_profile/global")
    async def patch_global_profile(request: Request, room_id: str):
        room = room_of(room_id)
        need_write(request, room)
        store = room.holder("global", "", "")
        for name, raw in (await request.json()).get("variables", {}).items():
            definition(room, "global", name)
            set_value(store, name, parse_value(raw))
        return {"variables": store}

    @app.get(prefix + "/variables_profile/{scope}/{kind}/{entity}")
    async def get_profile(request: Request, room_id: str, scope: str, kind: str, entity: str):
        room = room_of(room_id)
        need_read(request, room)
        return reply(request, any_profile(room, scope, kind, entity))

    @app.patch(prefix + "/variables_profile/{scope}/{kind}/{entity}")
    async def patch_profile(request: Request, room_id: str, scope: str, kind: str, entity: str):
        room = room_of(room_id)
        need_write(request, room)
        any_profile(room, scope, kind, entity)
        store = room.holder(scope, kind, entity)
        for name, raw in (await request.json()).get("variables", {}).items():
            if raw is None:
                store.pop(name, None)
            else:
                definition(room, scope, name)
                set_value(store, name, parse_value(raw))
        return {holder_key(scope, kind): holder_object(room, scope, kind, entity), "variables": store}

    @app.delete(prefix + "/variables_profile/user/{kind}/{entity}")
    async def delete_profile(request: Request, room_id: str, kind: str, entity: str):
        room = room_of(room_id)
        need_write(request, room)
        any_profile(room, "user", kind, entity)
        room.values.pop(("user", kind, entity), None)
        return Response(status_code=204)

    return app


def _run_op(room: Room, scope: str, name: str, op: dict) -> dict:
    op_id = op.get("op_id")
    try:
        kind, _, entity = str(op.get("path", "")).partition("/")
        check_target(scope, kind)
        if not entity.isdigit():
            raise INVALID_TARGET
        store = room.holder(scope, kind, entity)
        method = op.get("method")
        if method == "GET":
            if name not in store:
                raise NOT_FOUND
            body = store[name]
        elif method == "PUT":
            body = set_value(store, name, parse_value(op.get("body", {}).get("value")))
        elif method == "PATCH":
            if name not in store:
                raise NOT_FOUND
            body = set_value(store, name, parse_value(op.get("body", {}).get("value")))
        elif method == "DELETE":
            if store.pop(name, None) is None:
                raise NOT_FOUND
            return {"status": 204, "body": None, "error": None, "op_id": op_id}
        else:
            raise INVALID_TARGET
        # Live: successful ops carry "error": null, and values are snapshots.
        return {"status": 200, "body": dict(body), "error": None, "op_id": op_id}
    except ApiError as exc:
        return {"status": exc.status, "body": None, "error": {"code": exc.code, "message": exc.code}, "op_id": op_id}
