"""Variables a real room provides on its own, such as @position.x. The list comes from a real room dump."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

_ROWS: list[dict[str, Any]] = json.loads(
    resources.files("wiredbench.engine").joinpath("internal_variables.json").read_text(encoding="utf-8")
)
_BY_NAME: dict[str, dict[str, dict[str, Any]]] = {}
for _row in _ROWS:
    _BY_NAME.setdefault(_row["name"], {})[_row["target"]] = _row
BY_ID = {row["id"]: row for row in _ROWS}


def rows() -> list[dict[str, Any]]:
    return list(_ROWS)


def targets(name: str) -> list[str]:
    """Who a name can belong to. Some, such as @position.x, exist on both furni and users."""
    return sorted(_BY_NAME.get(name, {}))


def row_for(name: str, target: str) -> dict[str, Any] | None:
    found = _BY_NAME.get(name, {})
    return found.get(target) or next(iter(found.values()), None)
