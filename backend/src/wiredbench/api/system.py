from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from wiredbench import __version__
from wiredbench.api.deps import Services, audit, get_db, get_services, public
from wiredbench.config import HOTELS, Hotel
from wiredbench.models import AuditEvent
from wiredbench.services import preferences

router = APIRouter(tags=["system"])


class PreferencesUpdate(BaseModel):
    default_hotel: Hotel | None = None
    gamedata_check: Literal["off", "startup", "daily"] | None = None
    cache_max_mb: int | None = Field(None, ge=16, le=102_400)
    session_hours: int | None = Field(None, ge=1, le=720)
    theme: Literal["system", "light", "dark"] | None = None


@router.api_route("/healthz", methods=["GET", "HEAD"])
@public
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/settings")
def get_settings(services: Services = Depends(get_services), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        **preferences.load(db, services.settings).model_dump(),
        "hotels": list(HOTELS),
        "version": __version__,
    }


@router.patch("/api/settings")
def update_settings(
    body: PreferencesUpdate,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    current = preferences.load(db, services.settings)
    updated = current.model_copy(update=body.model_dump(exclude_unset=True, exclude_none=True))
    preferences.save(db, updated)
    audit(db, request, "settings_update", ", ".join(sorted(body.model_fields_set)))
    db.commit()
    services.assets.enforce_limit(updated.cache_max_mb * 2**20)
    return {**updated.model_dump(), "hotels": list(HOTELS), "version": __version__}


@router.get("/api/cache")
def cache_info(services: Services = Depends(get_services), db: Session = Depends(get_db)) -> dict[str, Any]:
    gamedata = services.settings.gamedata_dir
    gamedata_bytes = (
        sum(path.stat().st_size for path in gamedata.rglob("*") if path.is_file()) if gamedata.exists() else 0
    )
    return {
        "assets_bytes": services.assets.size_bytes(),
        "gamedata_bytes": gamedata_bytes,
        "limit_bytes": preferences.load(db, services.settings).cache_max_mb * 2**20,
    }


@router.post("/api/cache/clear")
def cache_clear(
    request: Request, services: Services = Depends(get_services), db: Session = Depends(get_db)
) -> dict[str, int]:
    removed = services.assets.clear()
    audit(db, request, "cache_clear", f"{removed} files")
    db.commit()
    return {"removed": removed}


@router.get("/api/audit")
def audit_log(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(50))
    return [{"at": e.at, "actor": e.actor, "action": e.action, "target": e.target} for e in rows]
