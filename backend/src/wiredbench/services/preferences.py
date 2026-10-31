"""Settings changed from the app. Values from the environment are only the starting point."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wiredbench.config import Hotel, Settings
from wiredbench.models import Preference

KEY = "preferences"


class Preferences(BaseModel):
    default_hotel: Hotel
    gamedata_check: Literal["off", "startup", "daily"] = "off"
    cache_max_mb: int = Field(ge=16, le=102_400)
    session_hours: int = Field(ge=1, le=720)
    theme: Literal["system", "light", "dark"] = "system"


def load(db: Session, settings: Settings) -> Preferences:
    defaults = {
        "default_hotel": settings.default_hotel,
        "cache_max_mb": settings.cache_max_mb,
        "session_hours": settings.session_hours,
    }
    row = db.get(Preference, KEY)
    return Preferences.model_validate({**defaults, **(row.value if row else {})})


def save(db: Session, preferences: Preferences) -> None:
    row = db.get(Preference, KEY)
    if row:
        row.value = preferences.model_dump()
    else:
        db.add(Preference(key=KEY, value=preferences.model_dump()))
    db.flush()
