"""Database tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite drops time zones, so values are stored as UTC and read back as aware datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC).replace(tzinfo=None) if value else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value else None


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    password_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_user.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(255), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


class Preference(Base):
    __tablename__ = "preference"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Folder(Base):
    __tablename__ = "folder"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folder.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    trash_batch: Mapped[str | None] = mapped_column(String(32))
    trash_root: Mapped[bool] = mapped_column(Boolean, default=False)


class Sandbox(Base):
    __tablename__ = "sandbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folder.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="sandbox")
    hotel: Mapped[str] = mapped_column(String(16))
    document: Mapped[Any] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    catalog_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    trash_batch: Mapped[str | None] = mapped_column(String(32))
    trash_root: Mapped[bool] = mapped_column(Boolean, default=False)


class SandboxVersion(Base):
    __tablename__ = "sandbox_version"
    __table_args__ = (Index("ix_sandbox_version_unique", "sandbox_id", "revision", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandbox.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    document: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class GamedataState(Base):
    __tablename__ = "gamedata_state"

    hotel: Mapped[str] = mapped_column(String(16), primary_key=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_result: Mapped[str | None] = mapped_column(String(32))
    last_error: Mapped[str | None] = mapped_column(String(255))
    last_auto_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class CatalogVersion(Base):
    __tablename__ = "catalog_version"
    __table_args__ = (
        Index("ix_catalog_version_hotel_sha", "hotel", "sha256", unique=True),
        Index(
            "ix_catalog_version_one_current", "hotel", unique=True, sqlite_where=text("status = 'current'")
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel: Mapped[str] = mapped_column(String(16), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending, dismissed, current, archived.
    base_version_id: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    item_count: Mapped[int] = mapped_column(Integer)
    wired_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_path: Mapped[str] = mapped_column(String(255))


class CatalogItem(Base):
    __tablename__ = "catalog_item"
    __table_args__ = (
        Index("ix_catalog_item_version_class", "version_id", "classname", unique=True),
        Index("ix_catalog_item_version_wired", "version_id", "is_wired", "wired_type"),
        Index("ix_catalog_item_class_revision", "classname", "revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("catalog_version.id", ondelete="CASCADE"))
    classname: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(8))  # floor or wall.
    furni_id: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    furniline: Mapped[str] = mapped_column(String(64), default="")
    xdim: Mapped[int] = mapped_column(Integer, default=1)
    ydim: Mapped[int] = mapped_column(Integer, default=1)
    height: Mapped[float | None] = mapped_column(Float)
    is_wired: Mapped[bool] = mapped_column(Boolean, default=False)
    wired_type: Mapped[str | None] = mapped_column(String(16))
    release_stage: Mapped[str] = mapped_column(String(24), default="live")
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[Any] = mapped_column(JSON)
