from __future__ import annotations

import httpx

from . import __version__
from .config import AgentIdentity, InstallConfig
from .metrics import collect_hello


def enroll(install: InstallConfig) -> AgentIdentity:
    hello = collect_hello()
    payload = {
        "enrollment_token": install.enrollment_token,
        "hostname": hello["hostname"],
        "os": hello.get("os"),
        "os_version": hello.get("os_version"),
        "arch": hello.get("arch"),
        "agent_version": __version__,
        "primary_ip": hello.get("primary_ip"),
        "mac_addresses": hello.get("mac_addresses") or [],
    }
    with httpx.Client(verify=install.verify_tls, timeout=30) as client:
        resp = client.post(f"{install.server_url}/api/v1/agents/enroll", json=payload)
        resp.raise_for_status()
        body = resp.json()

    return AgentIdentity(
        endpoint_id=body["endpoint_id"],
        agent_token=body["agent_token"],
        server_url=install.server_url,
        websocket_url=body["websocket_url"],
        heartbeat_interval_seconds=body.get("heartbeat_interval_seconds", 15),
    )
