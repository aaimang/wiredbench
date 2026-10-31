from __future__ import annotations

import hashlib
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services
from wiredbench.config import Hotel
from wiredbench.errors import ApiError, not_found
from wiredbench.services import furnidata, preferences
from wiredbench.services.catalog import version_dict
from wiredbench.services.upstream import UpstreamError

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class SyncRequest(BaseModel):
    hotel: Hotel
    force: bool = False


class VersionRequest(BaseModel):
    version_id: int = Field(gt=0)


def _hotel_or_default(hotel: Hotel | None, services: Services, db: Session) -> str:
    return hotel or preferences.load(db, services.settings).default_hotel


@router.get("/status")
def status(
    hotel: Hotel | None = None, services: Services = Depends(get_services), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return services.catalog.status(_hotel_or_default(hotel, services, db))


@router.post("/sync")
def sync(
    body: SyncRequest,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = services.catalog.sync(body.hotel, force=body.force)
    audit(db, request, "catalog_sync", f"{body.hotel}: {result['result']}")
    db.commit()
    return {**result, "status": services.catalog.status(body.hotel)}


@router.get("/diff/{from_id}/{to_id}")
def diff(
    from_id: int,
    to_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    entries = services.catalog.diff(from_id, to_id)
    return {
        "from_id": from_id,
        "to_id": to_id,
        "summary": furnidata.summarise(entries),
        "total": len(entries),
        "entries": entries[offset : offset + limit],
    }


@router.post("/apply")
def apply(
    body: VersionRequest,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    version = services.catalog.apply(body.version_id)
    audit(db, request, "catalog_apply", f"{version.hotel}: version {version.id}")
    db.commit()
    return version_dict(version)


@router.post("/dismiss", status_code=204)
def dismiss(
    body: VersionRequest,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> None:
    services.catalog.dismiss(body.version_id)
    audit(db, request, "catalog_dismiss", f"version {body.version_id}")
    db.commit()


@router.post("/rollback")
def rollback(
    body: VersionRequest,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    version = services.catalog.rollback(body.version_id)
    audit(db, request, "catalog_rollback", f"{version.hotel}: version {version.id}")
    db.commit()
    return version_dict(version)


@router.get("/items")
def items(
    request: Request,
    response: Response,
    hotel: Hotel | None = None,
    q: str = Query("", max_length=120),
    scope: Literal["wired", "all"] = "wired",
    wired_type: Literal["trigger", "effect", "condition", "selector", "addon", "variable", "utility"]
    | None = None,
    stage: Literal["live", "not_in_catalogue", "new"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> Any:
    chosen = _hotel_or_default(hotel, services, db)
    # Items in a version never change, so the version and the query fully identify the response.
    sha = services.catalog.current_sha(chosen)
    key = hashlib.sha256(f"{sha}|{chosen}|{request.url.query}".encode()).hexdigest()[:32]
    etag = f'W/"{key}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return services.catalog.search(chosen, q, scope, wired_type, stage, offset, limit)


@router.get("/items/{classname}")
def item(
    classname: str,
    hotel: Hotel | None = None,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return services.catalog.item(_hotel_or_default(hotel, services, db), classname)


@router.get("/icons/{revision}/{classname}")
async def icon(revision: int, classname: str, services: Services = Depends(get_services)) -> FileResponse:
    # Only what the catalogue lists can reach Habbo, so this is not an open proxy.
    if not await run_in_threadpool(services.catalog.item_exists, classname, revision):
        raise not_found("Icon")
    try:
        path = await run_in_threadpool(services.assets.icon, revision, classname)
    except UpstreamError as exc:
        raise ApiError(502, "upstream_unavailable", "Could not download this icon.") from exc
    if path is None:
        raise not_found("Icon")
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )
