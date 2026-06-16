from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    role: str
    totp_enabled: bool


# --- Enrollment ---

class EnrollmentTokenCreate(BaseModel):
    label: str | None = None
    max_uses: int = Field(default=1, ge=1, le=10_000)
    ttl_minutes: int | None = Field(default=60 * 24, ge=1)
    default_tags: list[str] = Field(default_factory=list)


class EnrollmentTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    token: str
    label: str | None
    max_uses: int
    uses: int
    expires_at: datetime | None
    revoked: bool
    default_tags: list[str]
    created_at: datetime


class AgentEnrollRequest(BaseModel):
    enrollment_token: str
    hostname: str
    os: str | None = None
    os_version: str | None = None
    arch: str | None = None
    agent_version: str | None = None
    primary_ip: str | None = None
    mac_addresses: list[str] = Field(default_factory=list)


class AgentEnrollResponse(BaseModel):
    endpoint_id: uuid.UUID
    agent_token: str
    websocket_url: str
    heartbeat_interval_seconds: int = 15


# --- Endpoints ---

class EndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hostname: str
    os: str | None
    os_version: str | None
    arch: str | None
    agent_version: str | None
    primary_ip: str | None
    tags: list[str]
    notes: str | None
    last_seen_at: datetime | None
    enrolled_at: datetime
    latest_metrics: dict[str, Any] | None
    online: bool


class EndpointUpdate(BaseModel):
    tags: list[str] | None = None
    notes: str | None = None
