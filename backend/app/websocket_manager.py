"""In-memory registry of live agent and UI WebSocket connections.

Single-process for MVP. When we scale to multiple backend workers we'll swap this
for Redis pub/sub so any worker can route a command to the agent connected to
any other worker.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class AgentConnection:
    endpoint_id: uuid.UUID
    websocket: WebSocket
    connected_at: float
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_json(self, payload: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.websocket.send_text(json.dumps(payload))


class ConnectionManager:
    def __init__(self) -> None:
        self._agents: dict[uuid.UUID, AgentConnection] = {}
        self._ui_clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    # --- Agents ---

    async def register_agent(self, endpoint_id: uuid.UUID, websocket: WebSocket) -> AgentConnection:
        import time

        conn = AgentConnection(endpoint_id=endpoint_id, websocket=websocket, connected_at=time.time())
        async with self._lock:
            # If another connection for this endpoint exists, close it first.
            existing = self._agents.get(endpoint_id)
            if existing is not None:
                try:
                    await existing.websocket.close(code=4000, reason="superseded")
                except Exception:
                    pass
            self._agents[endpoint_id] = conn
        await self.broadcast_ui({"type": "endpoint.online", "endpoint_id": str(endpoint_id)})
        return conn

    async def unregister_agent(self, endpoint_id: uuid.UUID, conn: AgentConnection) -> None:
        async with self._lock:
            # Only remove if this exact connection is still the registered one
            if self._agents.get(endpoint_id) is conn:
                del self._agents[endpoint_id]
                changed = True
            else:
                changed = False
        if changed:
            await self.broadcast_ui({"type": "endpoint.offline", "endpoint_id": str(endpoint_id)})

    def is_online(self, endpoint_id: uuid.UUID) -> bool:
        return endpoint_id in self._agents

    def online_ids(self) -> set[uuid.UUID]:
        return set(self._agents.keys())

    async def send_to_agent(self, endpoint_id: uuid.UUID, payload: dict[str, Any]) -> bool:
        conn = self._agents.get(endpoint_id)
        if conn is None:
            return False
        try:
            await conn.send_json(payload)
            return True
        except Exception:
            return False

    # --- UI clients ---

    async def register_ui(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._ui_clients.add(websocket)

    async def unregister_ui(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._ui_clients.discard(websocket)

    async def broadcast_ui(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in list(self._ui_clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._ui_clients.discard(ws)


manager = ConnectionManager()
