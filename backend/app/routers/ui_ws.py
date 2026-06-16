"""UI-facing WebSocket. Pushes endpoint status and heartbeat updates to the dashboard."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, status

from ..database import SessionLocal
from ..models import User
from ..security import decode_access_token
from ..websocket_manager import manager

router = APIRouter(tags=["ui-ws"])


@router.websocket("/api/v1/ws")
async def ui_ws(websocket: WebSocket, token: str | None = Query(default=None)):
    # Browsers can't set custom headers on WebSocket upgrades, so we take the
    # JWT as a query param. Clients should use wss:// so it's not exposed in logs.
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = decode_access_token(token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    sub = payload.get("sub")
    if not sub:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(sub))
        if not user or user.disabled:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    await manager.register_ui(websocket)

    # Send the current online set on connect so the UI can reconcile
    await websocket.send_json(
        {"type": "online.snapshot", "endpoint_ids": [str(i) for i in manager.online_ids()]}
    )

    try:
        while True:
            # We don't expect UI -> server messages yet, but we must read to keep the
            # connection alive and detect close.
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await manager.unregister_ui(websocket)
