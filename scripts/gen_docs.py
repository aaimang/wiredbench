"""Writes the generated README sections, or with --check fails if they are out of date."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.routing import APIRoute
from pydantic_core import PydanticUndefined

from wiredbench.api import ROUTERS
from wiredbench.config import Settings

README = Path(__file__).parents[1] / "README.md"


def env_table() -> str:
    rows = ["| Variable | Default | Purpose |", "|---|---|---|"]
    for name, field in Settings.model_fields.items():
        default = "" if field.default in (None, PydanticUndefined) else f"`{field.default}`"
        rows.append(f"| `WB_{name.upper()}` | {default} | {field.description} |")
    return "\n".join(rows)


def api_table() -> str:
    rows = ["| Method | Path | Access |", "|---|---|---|"]
    routes = [route for router in ROUTERS for route in router.routes if isinstance(route, APIRoute)]
    for route in sorted(routes, key=lambda r: (r.path, sorted(r.methods))):
        access = "Public" if getattr(route.endpoint, "__wb_public__", False) else "Admin"
        methods = ", ".join(sorted(route.methods - {"HEAD"}))
        rows.append(f"| {methods} | `{route.path}` | {access} |")
    return "\n".join(rows)


def render(text: str) -> str:
    for name, body in (("env", env_table()), ("api", api_table())):
        pattern = rf"(<!-- generated:{name} -->\n).*?(<!-- /generated:{name} -->)"
        text, count = re.subn(pattern, lambda m, b=body: f"{m.group(1)}{b}\n{m.group(2)}", text, flags=re.S)
        if count != 1:
            sys.exit(f"README.md needs one generated:{name} section.")
    return text


def main() -> None:
    current = README.read_text(encoding="utf-8")
    updated = render(current)
    if "--check" in sys.argv:
        if current != updated:
            sys.exit("README.md is out of date. Run: uv run python scripts/gen_docs.py")
        return
    README.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
