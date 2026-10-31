"""Request guard and shared dependencies.

Every route runs through guard(), so a new route needs a login and a CSRF token unless it is
explicitly marked @public. Forgetting a check therefore fails closed.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from wiredbench.config import Settings
from wiredbench.engine.sessions import RunRegistry
from wiredbench.errors import ApiError
from wiredbench.models import AdminUser, AuditEvent, AuthSession, utcnow
from wiredbench.security import SESSION_COOKIE, RateLimiter, hash_token, same_origin
from wiredbench.services.assets import AssetCache
from wiredbench.services.catalog import CatalogService

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def public[F: Callable[..., Any]](endpoint: F) -> F:
    """Marks a route as reachable without a login."""
    endpoint.__wb_public__ = True  # type: ignore[attr-defined]
    return endpoint


@dataclass
class Services:
    settings: Settings
    sessions: Any
    catalog: CatalogService
    assets: AssetCache
    login_ip_limiter: RateLimiter
    login_user_limiter: RateLimiter
    write_limiter: RateLimiter
    read_limiter: RateLimiter
    runs: RunRegistry


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def get_db(services: Services = Depends(get_services)) -> Iterator[Session]:
    with services.sessions() as db:
        yield db


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def guard(
    request: Request, services: Services = Depends(get_services), db: Session = Depends(get_db)
) -> None:
    unsafe = request.method not in SAFE_METHODS
    limiter = services.write_limiter if unsafe else services.read_limiter
    if retry := limiter.hit(client_ip(request)):
        raise ApiError(429, "rate_limited", "Too many requests. Try again shortly.", retry)

    origin = request.headers.get("origin")
    if unsafe and origin and not same_origin(origin, services.settings.public_url):
        raise ApiError(403, "bad_origin", "This request came from another site.")

    endpoint = request.scope.get("endpoint")
    if getattr(endpoint, "__wb_public__", False):
        return

    token = request.cookies.get(SESSION_COOKIE)
    session = db.get(AuthSession, hash_token(token)) if token else None
    if session is None or session.expires_at <= utcnow():
        raise ApiError(401, "not_logged_in", "Log in to continue.")
    user = db.get(AdminUser, session.user_id)
    if user is None:
        raise ApiError(401, "not_logged_in", "Log in to continue.")
    if unsafe and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
        raise ApiError(403, "bad_csrf", "This page is out of date. Reload and try again.")
    request.state.session = session
    request.state.user = user
    db.commit()  # Returns the connection to the pool, because a page of icons can wait on Habbo for a while.


def current_user(request: Request) -> AdminUser:
    user: AdminUser = request.state.user
    return user


def audit(db: Session, request: Request, action: str, target: str = "", actor: str | None = None) -> None:
    user = getattr(request.state, "user", None)
    name = actor or (user.username if user else "anonymous")
    db.add(AuditEvent(actor=name[:64], action=action, target=target[:255], ip=client_ip(request)))
