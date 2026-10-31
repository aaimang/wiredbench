from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from wiredbench.api.deps import Services, audit, client_ip, current_user, get_db, get_services, public, viewer
from wiredbench.errors import ApiError
from wiredbench.models import AdminUser, AuthSession, utcnow
from wiredbench.security import (
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    hash_password,
    hash_token,
    new_token,
    verify_password,
)
from wiredbench.services import preferences

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)


def _me(user: AdminUser, session: AuthSession) -> dict[str, Any]:
    return {
        "username": user.username,
        "csrf_token": session.csrf_token,
        "expires_at": session.expires_at,
        "view_as": session.view_as,
    }


@router.post("/login")
@public
def login(
    body: Login,
    request: Request,
    response: Response,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    checks = (
        (services.login_ip_limiter, client_ip(request)),
        (services.login_user_limiter, body.username.lower()),
    )
    if retry := max(limiter.retry_after(key) for limiter, key in checks):
        raise ApiError(
            429, "too_many_logins", f"Too many failed logins. Try again in {retry // 60 + 1} minutes.", retry
        )

    user = db.scalar(select(AdminUser).where(AdminUser.username == body.username))
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        for limiter, key in checks:
            limiter.record(key)
        audit(db, request, "login_failed", actor=body.username or "unknown")
        db.commit()
        raise ApiError(401, "bad_credentials", "That username or password is wrong.")

    for limiter, key in checks:
        limiter.reset(key)
    prefs = preferences.load(db, services.settings)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    token = new_token()
    session = AuthSession(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=new_token(),
        expires_at=utcnow() + timedelta(hours=prefs.session_hours),
    )
    db.add(session)
    request.state.user = user
    audit(db, request, "login")
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=prefs.session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=services.settings.secure_cookies,
        path="/",
    )
    return _me(user, session)


@router.post("/logout", status_code=204)
@viewer
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == request.state.session.token_hash))
    audit(db, request, "logout")
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
@viewer
def me(request: Request, user: AdminUser = Depends(current_user)) -> dict[str, Any]:
    return _me(user, request.state.session)


def _set_view_as(request: Request, db: Session, on: bool) -> dict[str, Any]:
    session = db.get(AuthSession, request.state.session.token_hash)
    if session is None:
        raise ApiError(401, "not_logged_in", "Log in to continue.")
    session.view_as = on
    audit(db, request, "view_as_start" if on else "view_as_stop")
    db.commit()
    return _me(request.state.user, session)


@router.post("/view-as")
def start_view_as(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _set_view_as(request, db, True)


@router.delete("/view-as")
@viewer
def stop_view_as(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _set_view_as(request, db, False)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange,
    request: Request,
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> None:
    stored = db.get(AdminUser, user.id)
    if stored is None or not verify_password(stored.password_hash, body.current_password):
        raise ApiError(403, "bad_credentials", "Your current password is wrong.")
    stored.password_hash = hash_password(body.new_password)
    stored.password_changed_at = utcnow()
    # Signs out everywhere else, in case the old password leaked.
    db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.token_hash != request.state.session.token_hash
        )
    )
    audit(db, request, "password_changed")
    db.commit()
    services.settings.initial_password_path.unlink(missing_ok=True)
