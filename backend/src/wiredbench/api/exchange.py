from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, get_db, get_services
from wiredbench.config import HOTELS, Hotel
from wiredbench.errors import ApiError
from wiredbench.services import exchange, preferences, room
from wiredbench.services import workspace as ws

router = APIRouter(prefix="/api", tags=["exchange"])


class ImportFile(BaseModel):
    file: dict[str, Any]
    name: str | None = Field(None, min_length=1, max_length=100)
    folder_id: int | None = None
    hotel: Hotel | None = None


def _details(services: Services, hotel: str, document: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    details: dict[str, dict[str, Any] | None] = {}
    for classname in {item["classname"] for item in document.get("furni", [])}:
        try:
            details[classname] = services.catalog.item(hotel, classname)
        except ApiError:
            details[classname] = None
    return details


def _filename(name: str, suffix: str) -> str:
    safe = re.sub(r"[^\w.-]+", "-", name, flags=re.ASCII).strip("-.") or "room"
    return f"{safe[:80]}{suffix}.json"


@router.post("/import", status_code=201)
def import_room(
    body: ImportFile,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    kind = exchange.detect(body.file)
    report: dict[str, Any] = {"format": "native", "warnings": []}
    hotel: str | None = body.hotel
    name, description = body.name, ""
    if kind == "native":
        document = exchange.read_native(body.file)
        file_hotel = body.file.get("hotel")
        if hotel is None and isinstance(file_hotel, str):
            hotel = file_hotel
        file_name = body.file.get("name")
        name = name or (file_name[:100] if isinstance(file_name, str) and file_name.strip() else None)
        text = body.file.get("description")
        description = text[:2000] if isinstance(text, str) else ""
    else:
        document, report = exchange.import_gpresets(body.file)
    prefs = preferences.load(db, services.settings)
    hotel = hotel or prefs.default_hotel
    if hotel not in HOTELS:
        hotel = prefs.default_hotel
    room.validate(document)
    final_name = ws.free_name(db, name or "Imported room", body.folder_id, "sandbox", "copy")
    sandbox = ws.create_sandbox(db, final_name, body.folder_id, description, hotel, None)
    ws.save_document(db, sandbox.id, document, sandbox.revision, services.catalog.current_sha(hotel))
    rows = exchange.shopping_list(document, _details(services, hotel, document))
    missing = [row["classname"] for row in rows if row["stage"] == "unknown"]
    if missing:
        report["warnings"].append(
            f"{len(missing)} furni types are not in this hotel's catalogue, so they show as missing."
        )
    audit(db, request, "room_import", final_name)
    db.commit()
    return {**ws.sandbox_summary(sandbox), "report": report}


@router.get("/sandboxes/{sandbox_id}/export")
def export_room(
    sandbox_id: int,
    request: Request,
    format: Literal["native", "gpresets"] = Query("native"),
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Room data only. API keys live in another table, so they cannot end up in a file."""
    sandbox = ws.live_sandbox(db, sandbox_id)
    document = sandbox.document if isinstance(sandbox.document, dict) else {}
    rows = exchange.shopping_list(document, _details(services, sandbox.hotel, document))
    warnings: list[str] = []
    if format == "native":
        file = exchange.export_native(sandbox.name, sandbox.hotel, sandbox.description, document)
        filename = _filename(sandbox.name, ".wiredbench")
    else:
        file, warnings = exchange.export_gpresets(document)
        warnings += exchange.obtainable_warnings(rows)
        filename = _filename(sandbox.name, "")
    audit(db, request, "room_export", f"{sandbox.name} ({format})")
    db.commit()
    return {"filename": filename, "file": file, "report": {"shopping_list": rows, "warnings": warnings}}
