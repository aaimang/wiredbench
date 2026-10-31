"""Creates the single admin on first start."""

from __future__ import annotations

import logging
import os
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from wiredbench.config import Settings
from wiredbench.models import AdminUser
from wiredbench.security import MIN_PASSWORD_LENGTH, hash_password

log = logging.getLogger("wiredbench.admin")


def ensure_admin(db: Session, settings: Settings) -> None:
    if db.scalar(select(AdminUser.id).limit(1)) is not None:
        return
    if settings.admin_password_file:
        password = settings.admin_password_file.read_text(encoding="utf-8").strip()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"WB_ADMIN_PASSWORD_FILE must hold at least {MIN_PASSWORD_LENGTH} characters.")
    else:
        password = secrets.token_urlsafe(18)
        path = settings.initial_password_path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(password + "\n")
        # The path only: the password itself must never reach logs.
        log.warning("Created admin %r. First-login details are in %s", settings.admin_username, path)
    db.add(AdminUser(username=settings.admin_username, password_hash=hash_password(password)))
    db.commit()
