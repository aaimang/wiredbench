"""Checks a sandbox's room document before it is saved.

Only the fields the room uses are checked. Anything else is kept as it is, so that newer or imported
data is never lost.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from wiredbench.config import Hotel
from wiredbench.errors import ApiError
from wiredbench.services.assets import FIGURE
from wiredbench.services.furnidata import CLASSNAME

MAX_ROOM_SIZE = 64
MAX_Z = 40

Tile = Annotated[int, Field(ge=0, lt=MAX_ROOM_SIZE)]
Height = Annotated[float, Field(ge=0, le=MAX_Z)]
Direction = Annotated[int, Field(ge=0, le=7)]


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class RoomSize(_Open):
    width: int = Field(ge=1, le=MAX_ROOM_SIZE)
    height: int = Field(ge=1, le=MAX_ROOM_SIZE)
    timezone: str | None = Field(None, max_length=64)


class PlacedFurni(_Open):
    id: int = Field(ge=1)
    classname: Annotated[str, StringConstraints(pattern=f"^{CLASSNAME.pattern}$")]
    x: Tile
    y: Tile
    z: Height = 0
    rot: Direction = 0
    state: int = Field(0, ge=0, le=9999)
    wired: dict[str, Any] | None = None


class PlacedAvatar(_Open):
    id: int = Field(ge=1)
    name: str = Field(max_length=32)
    hotel: Hotel
    figure: Annotated[str, StringConstraints(pattern=f"^{FIGURE.pattern}$", max_length=400)]
    x: Tile
    y: Tile
    z: Height = 0
    dir: Direction = 2
    pose: Literal["std", "sit", "lay"] = "std"
    details: dict[str, int] | None = None


class RoomDocument(_Open):
    schema_version: int | None = Field(None, alias="schema")
    room: RoomSize | None = None
    furni: list[PlacedFurni] = Field(default_factory=list, max_length=5000)
    avatars: list[PlacedAvatar] = Field(default_factory=list, max_length=25)


def known_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def validate(document: dict[str, Any]) -> None:
    try:
        RoomDocument.model_validate(document)
    except ValidationError as exc:
        where = ".".join(str(part) for part in exc.errors()[0]["loc"])
        raise ApiError(422, "invalid_room", f"The room has a bad value at {where}.") from exc
    room = document.get("room")
    if room and room.get("timezone") and not known_timezone(room["timezone"]):
        raise ApiError(422, "invalid_room", "The room's time zone is not one we know.")
    if room:
        for key in ("furni", "avatars"):
            for item in document.get(key, []):
                if item["x"] >= room["width"] or item["y"] >= room["height"]:
                    raise ApiError(422, "invalid_room", "Something is placed outside the room.")
