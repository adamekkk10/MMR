from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("admin", "operator", "readonly", name="user_role"),
        nullable=False,
        default="admin",
    )
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnrollmentToken(Base):
    """Short-lived token minted by an admin, baked into an installer, consumed once by an agent."""

    __tablename__ = "enrollment_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    # The token the agent authenticates with on every WebSocket connect.
    # In a later iteration this gets replaced by mTLS certs issued at enrollment time.
    agent_token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arch: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mac_addresses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    latest_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    heartbeats: Mapped[list["Heartbeat"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class Heartbeat(Base):
    """Historical heartbeat snapshots. Trim aggressively in prod; this is the raw time-series."""

    __tablename__ = "heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    cpu_percent: Mapped[float | None] = mapped_column(nullable=True)
    mem_percent: Mapped[float | None] = mapped_column(nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    endpoint: Mapped[Endpoint] = relationship(back_populates="heartbeats")


class AuditLog(Base):
    """Immutable record of panel actions. Never updated, only appended."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
