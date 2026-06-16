from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
from typing import Any

import websockets

from . import __version__
from .config import AgentIdentity
from .metrics import collect_heartbeat, collect_hello

log = logging.getLogger("rmm_agent.client")


class AgentClient:
    def __init__(self, identity: AgentIdentity, *, verify_tls: bool = True) -> None:
        self.identity = identity
        self.verify_tls = verify_tls
        self._send_lock = asyncio.Lock()

    async def run_forever(self) -> None:
        """Reconnect loop with jittered exponential backoff."""
        delay = 1.0
        while True:
            try:
                await self._run_once()
                delay = 1.0  # reset after a clean disconnect
            except Exception as e:
                log.warning("Connection error: %s", e)
            sleep_for = min(60.0, delay) * (0.75 + random.random() * 0.5)
            log.info("Reconnecting in %.1fs", sleep_for)
            await asyncio.sleep(sleep_for)
            delay = min(60.0, delay * 2)

    async def _run_once(self) -> None:
        ssl_ctx: ssl.SSLContext | None = None
        if self.identity.websocket_url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context()
            if not self.verify_tls:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

        headers = [("Authorization", f"Bearer {self.identity.agent_token}")]

        async with websockets.connect(
            self.identity.websocket_url,
            additional_headers=headers,
            ssl=ssl_ctx,
            ping_interval=30,
            ping_timeout=30,
            max_size=8 * 1024 * 1024,
        ) as ws:
            log.info("Connected to %s", self.identity.websocket_url)

            # Send hello with the latest system info in case anything changed since enrollment
            await self._send(ws, {"type": "hello", "data": {**collect_hello(), "agent_version": __version__}})

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    await self._on_message(ws, msg)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self, ws) -> None:
        # Send an immediate heartbeat so the dashboard fills in fast, then tick.
        try:
            while True:
                payload = collect_heartbeat()
                await self._send(ws, {"type": "heartbeat", "data": payload})
                await asyncio.sleep(self.identity.heartbeat_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Heartbeat loop stopped: %s", e)

    async def _on_message(self, ws, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "welcome":
            interval = msg.get("heartbeat_interval_seconds")
            if isinstance(interval, int) and interval > 0:
                self.identity.heartbeat_interval_seconds = interval
            log.info("Server welcomed us as endpoint %s", msg.get("endpoint_id"))
        elif mtype == "ping":
            await self._send(ws, {"type": "pong"})
        elif mtype == "command":
            # TODO: dispatch remote commands (shell.exec, file.read, etc.) once those
            # subsystems land. For now, explicitly decline so operators see it in logs.
            await self._send(
                ws,
                {
                    "type": "result",
                    "request_id": msg.get("request_id"),
                    "data": {"ok": False, "error": "command dispatch not yet implemented"},
                },
            )

    async def _send(self, ws, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await ws.send(json.dumps(payload))
