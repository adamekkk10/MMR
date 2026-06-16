"""Agent-facing WebSocket endpoint.

Agents authenticate with the token they received at enrollment (Bearer header OR
`?token=` query param so browser-style clients can connect too; for production we
prefer the header).

Message protocol (JSON):

  agent -> server:
    {"type": "hello",      "data": {"agent_version": "...", "os": "...", ...}}
    {"type": "heartbeat",  "data": {"cpu_percent": 12.3, "mem_percent": 48.1, ...}}
    {"type": "pong"}
    {"type": "result",     "request_id": "<uuid>", "data": {...}}
    {"type": "log",        "level": "info|warn|error", "msg": "..."}

  server -> agent:
    {"type": "welcome", "endpoint_id": "<uuid>", "heartbeat_interval_seconds": 15}
    {"type": "ping"}
    {"type": "command", "request_id": "<uuid>", "command": "shell.exec", "args": {...}}
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from ..database import SessionLocal
from ..models import Endpoint, Heartbeat
from ..security import hash_agent_token
from ..websocket_manager import manager

router = APIRouter(tags=["agent-ws"])

HEARTBEAT_INTERVAL_SECONDS = 15


def _authenticate(token: str) -> Endpoint | None:
    if not token:
        return None
    token_hash = hash_agent_token(token)
    with SessionLocal() as db:
        ep = db.scalar(select(Endpoint).where(Endpoint.agent_token_hash == token_hash))
        if ep is None:
            return None
        # Detach so the caller can read fields without keeping the session open
        db.expunge(ep)
        return ep


@router.websocket("/api/v1/agents/ws")
async def agent_ws(websocket: WebSocket, token: str | None = Query(default=None)):
    # Prefer Authorization header, fall back to query param
    auth_header = websocket.headers.get("authorization", "")
    header_token = ""
    if auth_header.lower().startswith("bearer "):
        header_token = auth_header[7:].strip()
    supplied_token = header_token or (token or "")

    endpoint = _authenticate(supplied_token)
    if endpoint is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    conn = await manager.register_agent(endpoint.id, websocket)

    await conn.send_json(
        {
            "type": "welcome",
            "endpoint_id": str(endpoint.id),
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await _handle_agent_message(endpoint.id, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Swallow to ensure we always unregister
        pass
    finally:
        await manager.unregister_agent(endpoint.id, conn)


async def _handle_agent_message(endpoint_id: uuid.UUID, msg: dict) -> None:
    mtype = msg.get("type")
    if mtype == "heartbeat":
        await _handle_heartbeat(endpoint_id, msg.get("data") or {})
    elif mtype == "hello":
        await _handle_hello(endpoint_id, msg.get("data") or {})
    # "pong", "result", "log" are accepted but not yet processed in MVP


async def _handle_hello(endpoint_id: uuid.UUID, data: dict) -> None:
    fields = {
        k: data.get(k)
        for k in ("os", "os_version", "arch", "agent_version", "primary_ip")
        if data.get(k) is not None
    }
    mac_addresses = data.get("mac_addresses")
    with SessionLocal() as db:
        ep = db.get(Endpoint, endpoint_id)
        if ep is None:
            return
        for k, v in fields.items():
            setattr(ep, k, v)
        if isinstance(mac_addresses, list):
            ep.mac_addresses = mac_addresses
        db.commit()


async def _handle_heartbeat(endpoint_id: uuid.UUID, data: dict) -> None:
    now = datetime.now(timezone.utc)
    cpu = data.get("cpu_percent")
    mem = data.get("mem_percent")
    disk = data.get("disk_percent")

    with SessionLocal() as db:
        ep = db.get(Endpoint, endpoint_id)
        if ep is None:
            return
        ep.last_seen_at = now
        ep.latest_metrics = data
        db.add(
            Heartbeat(
                endpoint_id=endpoint_id,
                cpu_percent=cpu,
                mem_percent=mem,
                disk_percent=disk,
                payload=data,
            )
        )
        db.commit()

    await manager.broadcast_ui(
        {
            "type": "endpoint.heartbeat",
            "endpoint_id": str(endpoint_id),
            "last_seen_at": now.isoformat(),
            "metrics": data,
        }
    )
