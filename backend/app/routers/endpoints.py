from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record as audit
from ..database import get_db
from ..dependencies import CurrentUser, require_operator
from ..models import Endpoint
from ..schemas import EndpointOut, EndpointUpdate
from ..websocket_manager import manager

router = APIRouter(prefix="/api/v1/endpoints", tags=["endpoints"])


def _serialize(ep: Endpoint) -> EndpointOut:
    return EndpointOut(
        id=ep.id,
        hostname=ep.hostname,
        os=ep.os,
        os_version=ep.os_version,
        arch=ep.arch,
        agent_version=ep.agent_version,
        primary_ip=ep.primary_ip,
        tags=ep.tags or [],
        notes=ep.notes,
        last_seen_at=ep.last_seen_at,
        enrolled_at=ep.enrolled_at,
        latest_metrics=ep.latest_metrics,
        online=manager.is_online(ep.id),
    )


@router.get("", response_model=list[EndpointOut])
def list_endpoints(_: CurrentUser, db: Session = Depends(get_db)) -> list[EndpointOut]:
    rows = list(db.scalars(select(Endpoint).order_by(Endpoint.hostname)))
    return [_serialize(e) for e in rows]


@router.get("/{endpoint_id}", response_model=EndpointOut)
def get_endpoint(endpoint_id: uuid.UUID, _: CurrentUser, db: Session = Depends(get_db)) -> EndpointOut:
    ep = db.get(Endpoint, endpoint_id)
    if not ep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _serialize(ep)


@router.patch("/{endpoint_id}", response_model=EndpointOut)
def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: EndpointUpdate,
    user: Annotated[CurrentUser, Depends(require_operator)],
    db: Session = Depends(get_db),
) -> EndpointOut:
    ep = db.get(Endpoint, endpoint_id)
    if not ep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    changed: dict = {}
    if payload.tags is not None:
        ep.tags = payload.tags
        changed["tags"] = payload.tags
    if payload.notes is not None:
        ep.notes = payload.notes
        changed["notes"] = payload.notes
    db.commit()
    db.refresh(ep)
    audit(db, action="endpoint.update", actor=user, target_type="endpoint", target_id=str(ep.id), details=changed)
    return _serialize(ep)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(
    endpoint_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_operator)],
    db: Session = Depends(get_db),
) -> None:
    ep = db.get(Endpoint, endpoint_id)
    if not ep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(ep)
    db.commit()
    audit(db, action="endpoint.delete", actor=user, target_type="endpoint", target_id=str(endpoint_id))
