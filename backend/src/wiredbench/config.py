"""Install-level settings, read from WB_* environment variables or a local .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

HOTELS: dict[str, str] = {
    "com": "www.habbo.com",
    "com.br": "www.habbo.com.br",
    "de": "www.habbo.de",
    "es": "www.habbo.es",
    "fi": "www.habbo.fi",
    "fr": "www.habbo.fr",
    "it": "www.habbo.it",
    "nl": "www.habbo.nl",
    "com.tr": "www.habbo.com.tr",
    "sandbox": "sandbox.habbo.com",
}
Hotel = Literal["com", "com.br", "de", "es", "fi", "fr", "it", "nl", "com.tr", "sandbox"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WB_", env_file=".env", extra="ignore")

    data_dir: Path = Field(Path("data"), description="Folder for the database and caches.")
    host: str = Field("127.0.0.1", description="Address the server listens on.")
    port: int = Field(8000, description="Port the server listens on.")
    public_url: str = Field(
        "http://127.0.0.1:8000",
        description="Address people open in the browser. Used for origin and host checks and secure cookies.",
    )
    admin_username: str = Field(
        "admin", description="Admin login name, used when the admin is first created."
    )
    admin_password_file: Path | None = Field(
        None,
        description=(
            "File holding the initial admin password. If unset, a password is generated and "
            "saved to `<data_dir>/initial-admin-password`."
        ),
    )
    default_hotel: Hotel = Field("sandbox", description="Hotel selected until changed in Settings.")
    cache_max_mb: int = Field(512, ge=16, description="Initial furni asset cache limit, in MB.")
    session_hours: int = Field(168, ge=1, le=720, description="Initial login lifetime, in hours.")
    rate_limit_login: int = Field(5, ge=1, description="Failed logins allowed per address per 15 minutes.")
    rate_limit_writes: int = Field(240, ge=1, description="Write requests allowed per address per minute.")
    rate_limit_reads: int = Field(3000, ge=1, description="Read requests allowed per address per minute.")
    rate_limit_ticks: int = Field(
        1200, ge=1, description="Clock ticks from running rooms allowed per address per minute."
    )
    rate_limit_mock: int = Field(
        600, ge=1, description="Mock Web API requests allowed per address per minute."
    )
    tick_ms: int = Field(
        500, ge=50, le=5000, description="Initial WIRED engine tick length, in milliseconds."
    )
    audit_days: int = Field(90, ge=1, le=3650, description="Initial number of days to keep the activity log.")
    sync_cooldown_seconds: int = Field(30, ge=0, description="Minimum wait between manual checks per hotel.")
    max_gamedata_mb: int = Field(64, ge=1, description="Largest gamedata download accepted, in MB.")
    static_dir: Path | None = Field(None, description="Built frontend folder. Defaults to `frontend/dist`.")

    @field_validator("public_url")
    @classmethod
    def _valid_public_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("must be an http(s) URL")
        return value.rstrip("/")

    @property
    def secure_cookies(self) -> bool:
        return urlsplit(self.public_url).scheme == "https"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "wiredbench.db"

    @property
    def gamedata_dir(self) -> Path:
        return self.data_dir / "cache" / "gamedata"

    @property
    def furni_dir(self) -> Path:
        return self.data_dir / "cache" / "furni"

    @property
    def initial_password_path(self) -> Path:
        return self.data_dir / "initial-admin-password"

    @property
    def resolved_static_dir(self) -> Path:
        return self.static_dir or Path("frontend/dist")
