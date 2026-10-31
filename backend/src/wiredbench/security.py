"""Passwords, session tokens, rate limits, and origin checks."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
SESSION_COOKIE = "wb_session"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}

_hasher = PasswordHasher()
# Verified when a username is unknown, so a login takes the same time either way.
_dummy_hash = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _dummy_hash, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _origin_key(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    # localhost and 127.0.0.1 are the same machine, so either address works for a local install.
    return parts.scheme, "loopback" if host in LOOPBACK else host, parts.port


def same_origin(origin: str, public_url: str) -> bool:
    return _origin_key(origin) == _origin_key(public_url)


def allowed_hosts(public_url: str) -> list[str]:
    # Loopback names stay allowed for the container health check. They cannot be reached from outside.
    return sorted({urlsplit(public_url).hostname or "", "localhost", "127.0.0.1", "[::1]"})


class RateLimiter:
    """Sliding window per key. In memory, because the app runs as one process."""

    MAX_KEYS = 10_000

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _current(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self.MAX_KEYS:
                self._drop_stale(now)
            hits = self._hits[key] = deque()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def _drop_stale(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]
        if len(self._hits) >= self.MAX_KEYS:
            self._hits.clear()

    def retry_after(self, key: str) -> int:
        """Seconds until the key may try again; 0 if it is under the limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._current(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, int(hits[0] + self.window - now) + 1)

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._current(key, now).append(now)

    def hit(self, key: str) -> int:
        """Check and count one request in a single step. Returns retry_after."""
        now = time.monotonic()
        with self._lock:
            hits = self._current(key, now)
            if len(hits) >= self.limit:
                return max(1, int(hits[0] + self.window - now) + 1)
            hits.append(now)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
