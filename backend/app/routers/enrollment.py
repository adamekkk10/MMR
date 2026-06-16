"""Enrollment token management (admin) and agent enrollment (unauthenticated)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record as audit
from ..config import get_settings
from ..database import get_db
from ..dependencies import CurrentUser, require_admin
from ..models import Endpoint, EnrollmentToken
from ..schemas import (
    AgentEnrollRequest,
    AgentEnrollResponse,
    EnrollmentTokenCreate,
    EnrollmentTokenOut,
)
from ..security import generate_agent_token, generate_enrollment_token, hash_agent_token

settings = get_settings()

admin_router = APIRouter(prefix="/api/v1/enrollment-tokens", tags=["enrollment"])
public_router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@admin_router.post("", response_model=EnrollmentTokenOut, status_code=status.HTTP_201_CREATED)
def create_enrollment_token(
    payload: EnrollmentTokenCreate,
    user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> EnrollmentToken:
    expires_at = None
    if payload.ttl_minutes:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=payload.ttl_minutes)

    tok = EnrollmentToken(
        token=generate_enrollment_token(),
        label=payload.label,
        created_by=user.id,
        max_uses=payload.max_uses,
        uses=0,
        expires_at=expires_at,
        default_tags=payload.default_tags,
    )
    db.add(tok)
    db.commit()
    db.refresh(tok)

    audit(
        db,
        action="enrollment_token.create",
        actor=user,
        target_type="enrollment_token",
        target_id=str(tok.id),
        details={"label": tok.label, "max_uses": tok.max_uses},
    )
    return tok


@admin_router.get("", response_model=list[EnrollmentTokenOut])
def list_enrollment_tokens(
    _: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> list[EnrollmentToken]:
    return list(db.scalars(select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc())))


@admin_router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_enrollment_token(
    token_id: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> None:
    tok = db.get(EnrollmentToken, token_id)
    if not tok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    tok.revoked = True
    db.commit()
    audit(db, action="enrollment_token.revoke", actor=user, target_type="enrollment_token", target_id=str(tok.id))


@public_router.post("/enroll", response_model=AgentEnrollResponse)
def enroll_agent(
    payload: AgentEnrollRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentEnrollResponse:
    """Consume a one-shot enrollment token, return permanent agent credentials."""
    tok = db.scalar(select(EnrollmentToken).where(EnrollmentToken.token == payload.enrollment_token))
    source_ip = request.client.host if request.client else None

    def _bail(reason: str):
        audit(
            db,
            action="agent.enroll.failed",
            target_type="enrollment_token",
            target_id=tok.token if tok else payload.enrollment_token[:12] + "...",
            details={"hostname": payload.hostname, "reason": reason},
            source_ip=source_ip,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid enrollment token: {reason}")

    if not tok:
        _bail("unknown")
    if tok.revoked:
        _bail("revoked")
    if tok.expires_at and tok.expires_at < datetime.now(timezone.utc):
        _bail("expired")
    if tok.uses >= tok.max_uses:
        _bail("exhausted")

    agent_token = generate_agent_token()
    endpoint = Endpoint(
        agent_token_hash=hash_agent_token(agent_token),
        hostname=payload.hostname,
        os=payload.os,
        os_version=payload.os_version,
        arch=payload.arch,
        agent_version=payload.agent_version,
        primary_ip=payload.primary_ip or source_ip,
        mac_addresses=payload.mac_addresses,
        tags=list(tok.default_tags),
    )
    db.add(endpoint)
    tok.uses += 1
    db.commit()
    db.refresh(endpoint)

    audit(
        db,
        action="agent.enroll.success",
        target_type="endpoint",
        target_id=str(endpoint.id),
        details={"hostname": endpoint.hostname, "enrollment_token_id": str(tok.id)},
        source_ip=source_ip,
    )

    # Derive ws URL from the configured public URL
    ws_base = settings.public_url.replace("https://", "wss://").replace("http://", "ws://")
    return AgentEnrollResponse(
        endpoint_id=endpoint.id,
        agent_token=agent_token,
        websocket_url=f"{ws_base}/api/v1/agents/ws",
    )
