"""Agent config persistence.

`install_config.json` (read-only, shipped with the installer): server URL + enrollment token.
`agent.json` (writable, created on first successful enrollment): permanent endpoint ID and agent token.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    # On Linux, /var/lib/rmm-agent is standard for a system service.
    # On Windows we prefer ProgramData\RMM Agent.
    env = os.environ.get("RMM_AGENT_DATA_DIR")
    if env:
        return Path(env)
    if platform.system() == "Windows":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "RMM Agent"
    return Path("/var/lib/rmm-agent")


@dataclass
class InstallConfig:
    server_url: str
    enrollment_token: str
    verify_tls: bool = True
    tags: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "InstallConfig":
        data = json.loads(path.read_text())
        return cls(
            server_url=data["server_url"],
            enrollment_token=data["enrollment_token"],
            verify_tls=data.get("verify_tls", True),
            tags=data.get("tags", []),
        )


@dataclass
class AgentIdentity:
    endpoint_id: str
    agent_token: str
    server_url: str
    websocket_url: str
    heartbeat_interval_seconds: int = 15

    @classmethod
    def load(cls, path: Path) -> "AgentIdentity | None":
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        try:
            # Best-effort restrict permissions; the token is as sensitive as an SSH key.
            os.chmod(path, 0o600)
        except Exception:
            pass
