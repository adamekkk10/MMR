from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class BuildStatus(str, Enum):
    CACHED = "cached"
    BUILT = "built"
    FAILED = "failed"


@dataclass(frozen=True)
class BuildSpec:
    """Everything the build worker needs. Immutable so it can double as a cache key source."""

    # Values baked into the binary
    server_url: str
    enrollment_token: str
    verify_tls: bool = True
    tags: tuple[str, ...] = ()

    # Build-time metadata
    agent_version: str = "0.1.0"
    build_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # PyInstaller knobs
    console: bool = True  # Services benefit from console=True; GUI-subsystem silently swallows logging
    upx: bool = True
    strip: bool = True
    icon_path: Path | None = None  # .ico on disk, rendered into the .exe resource section

    # Windows version resource
    company_name: str = "RMM"
    product_name: str = "RMM Agent"
    file_description: str = "RMM endpoint agent"
    legal_copyright: str = ""

    # Signing (optional). If both set, osslsigncode post-processes the binary.
    signing_pfx_path: Path | None = None
    signing_pfx_password: str | None = None
    signing_timestamp_url: str = "http://timestamp.digicert.com"

    # Runner selection. "auto" prefers docker, falls back to native.
    runner: str = "auto"  # "auto" | "docker" | "native"
    docker_image: str = "rmm-builder:latest"  # built from Dockerfile.builder

    # Where to find the agent source tree (the dir containing `rmm_agent/`)
    agent_source_dir: Path = Path(__file__).resolve().parents[3] / "agent"

    def fingerprint(self) -> str:
        """Deterministic cache key input.

        Intentionally hashes the enrollment token directly: enrollment tokens are
        single-use and short-lived, so regenerating with the same token is a rare
        retry case where we *do* want to reuse the previous artifact. Build-irrelevant
        fields (build_id, timestamps) are excluded.
        """
        h = hashlib.sha256()
        for part in (
            self.server_url,
            self.enrollment_token,
            "1" if self.verify_tls else "0",
            ",".join(self.tags),
            self.agent_version,
            "1" if self.console else "0",
            "1" if self.upx else "0",
            "1" if self.strip else "0",
            str(self.icon_path or ""),
            self.company_name,
            self.product_name,
            self.file_description,
            self.legal_copyright,
            # Signing inputs change the artifact bytes too
            str(self.signing_pfx_path or ""),
            "1" if self.signing_pfx_password else "0",
        ):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()


@dataclass
class BuildResult:
    status: BuildStatus
    artifact_path: Path | None
    cache_key: str
    duration_seconds: float
    log_tail: str = ""
    error: str | None = None
    signed: bool = False
    size_bytes: int | None = None
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
