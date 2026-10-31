"""Runs the real app for browser tests, with Habbo replaced by files in WB_E2E_DIR. Never shipped."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import httpx
import uvicorn

from wiredbench.app import create_app
from wiredbench.config import Settings

ROOT = Path(os.environ["WB_E2E_DIR"])
FURNIDATA = ROOT / "furnidata.json"
# A 1x1 transparent PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def habbo(request: httpx.Request) -> httpx.Response:
    if request.url.host == "images.habbo.com":
        return httpx.Response(200, content=PNG)
    if not FURNIDATA.exists():
        return httpx.Response(503)
    body = FURNIDATA.read_bytes()
    digest = hashlib.sha256(body).hexdigest()[:16]
    if request.url.path.endswith("/1"):
        location = f"https://{request.url.host}/gamedata/furnidata_json/{digest}"
        return httpx.Response(307, headers={"location": location})
    etag = f'W/"{digest}"'
    if request.headers.get("if-none-match") == etag:
        return httpx.Response(304, headers={"etag": etag})
    return httpx.Response(200, content=body, headers={"etag": etag})


def main() -> None:
    port = int(sys.argv[1])
    password = ROOT / "password"
    password.write_text("e2e test password")
    settings = Settings(
        _env_file=None,
        data_dir=ROOT / "data",
        admin_password_file=password,
        public_url=f"http://127.0.0.1:{port}",
        sync_cooldown_seconds=0,
        rate_limit_login=50,
        static_dir=Path(__file__).parents[2] / "frontend" / "dist",
    )
    uvicorn.run(create_app(settings, transport=httpx.MockTransport(habbo)), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
