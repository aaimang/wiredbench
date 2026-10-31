"""Facts about real boxes, derived from unedited boxes in a real room. Numbers are defaults and carry no labels."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    text = resources.files("wiredbench.engine").joinpath("box_facts.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def of(classname: str) -> dict[str, Any] | None:
    fact: dict[str, Any] | None = load()["boxes"].get(classname)
    return fact
