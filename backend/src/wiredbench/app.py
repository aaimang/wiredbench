"""Application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from wiredbench import __version__
from wiredbench.api import ROUTERS
from wiredbench.api.deps import Services, guard, public
from wiredbench.api.mock import MockError
from wiredbench.config import Settings
from wiredbench.db import make_engine, make_session_factory, migrate
from wiredbench.engine.sessions import RunRegistry
from wiredbench.errors import ApiError, not_found
from wiredbench.models import AuditEvent, GamedataState, utcnow
from wiredbench.security import RateLimiter, allowed_hosts
from wiredbench.services import preferences
from wiredbench.services import workspace as ws
from wiredbench.services.admin import ensure_admin
from wiredbench.services.assets import AssetCache
from wiredbench.services.catalog import CatalogService
from wiredbench.services.upstream import Upstream

log = logging.getLogger("wiredbench")

MAX_BODY_BYTES = 2 * 2**20
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
        "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Robots-Tag": "noindex",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class BodyLimit:
    """Refuses oversized bodies before they are read, including chunked ones with no length header."""

    def __init__(self, app: ASGIApp, limit: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > self.limit:
            await self._too_large(scope, receive, send)
            return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise ApiError(413, "body_too_large", "This request is too large.")
            return message

        await self.app(scope, limited, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"error": "body_too_large", "message": "This request is too large."}, 413)
        await response(scope, receive, send)


class ImmutableStatic(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Any:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            # Vite puts a content hash in every asset name.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def maintenance(services: Services, startup: bool = False) -> None:
    """Hourly housekeeping: empties old trash and runs the automatic update check if one is due."""
    with services.sessions() as db:
        ws.purge_expired(db)
        prefs = preferences.load(db, services.settings)
        db.execute(delete(AuditEvent).where(AuditEvent.at < utcnow() - timedelta(days=prefs.audit_days)))
        db.commit()
    if prefs.gamedata_check == "off" or (prefs.gamedata_check == "startup" and not startup):
        return
    hotels = set(services.catalog.hotels_in_use()) | {prefs.default_hotel}
    for hotel in sorted(hotels):
        with services.sessions.begin() as db:
            state = db.get(GamedataState, hotel) or GamedataState(hotel=hotel)
            due = (
                startup
                or state.last_auto_check_at is None
                or utcnow() - state.last_auto_check_at >= timedelta(days=1)
            )
            if due:
                state.last_auto_check_at = utcnow()
                db.add(state)
        if due:
            # It only checks; applying an update is always the admin's decision.
            with suppress(ApiError):
                services.catalog.sync(hotel, manual=False)


def create_app(settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_path)
    migrate(engine)
    sessions = make_session_factory(engine)
    with sessions() as db:
        ensure_admin(db, settings)
        mock_rate = preferences.load(db, settings).rate_limit_mock
    upstream = Upstream(transport)
    services = Services(
        settings=settings,
        sessions=sessions,
        catalog=CatalogService(settings, sessions, upstream),
        assets=AssetCache(settings.furni_dir, upstream),
        login_ip_limiter=RateLimiter(settings.rate_limit_login, 15 * 60),
        # Higher, so that one address guessing passwords cannot lock the admin out.
        login_user_limiter=RateLimiter(settings.rate_limit_login * 4, 15 * 60),
        write_limiter=RateLimiter(settings.rate_limit_writes, 60),
        read_limiter=RateLimiter(settings.rate_limit_reads, 60),
        mock_limiter=RateLimiter(mock_rate, 60),
        runs=RunRegistry(),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def loop() -> None:
            startup = True
            while True:
                try:
                    await asyncio.to_thread(maintenance, services, startup)
                except Exception:
                    log.exception("Maintenance failed")
                startup = False
                await asyncio.sleep(3600)

        task = asyncio.create_task(loop())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        upstream.close()
        engine.dispose()

    # No interactive docs: every route is admin-only and the README lists them.
    app = FastAPI(
        title="Wiredbench",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(guard)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.services = services

    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(settings.public_url))

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return JSONResponse({"error": exc.code, "message": exc.message}, exc.status, headers=headers)

    @app.exception_handler(MockError)
    async def mock_error(_request: Request, exc: MockError) -> Response:
        # The live API answers an unknown scope with an empty 404 rather than its JSON error.
        return JSONResponse({"error": exc.code}, exc.status) if exc.code else Response(status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names and reasons only: the rejected values are never echoed back.
        fields = [
            {"field": ".".join(str(part) for part in e["loc"] if part != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        message = (
            fields[0]["message"].removeprefix("Value error, ") if fields else "This request is not valid."
        )
        return JSONResponse({"error": "invalid_request", "message": message, "fields": fields}, 422)

    for router in ROUTERS:
        app.include_router(router)
    _mount_frontend(app, settings.resolved_static_dir)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", ImmutableStatic(directory=assets), name="assets")
    root_files = {p.name: p for p in dist.iterdir() if p.is_file()} if dist.is_dir() else {}

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    @public
    def frontend(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            raise not_found("Route")
        if path in root_files and path != "index.html":
            return FileResponse(root_files[path], headers={"Cache-Control": "public, max-age=3600"})
        index = root_files.get("index.html")
        if index is None:
            return JSONResponse(
                {"error": "frontend_not_built", "message": "Run `npm run build` in frontend/."}, 503
            )
        # Not cached, so a new release's hashed assets are picked up straight away.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
