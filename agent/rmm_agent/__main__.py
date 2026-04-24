from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .client import AgentClient
from .config import AgentIdentity, InstallConfig, default_data_dir
from .enrollment import enroll

log = logging.getLogger("rmm_agent")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="rmm-agent", description="RMM endpoint agent")
    p.add_argument("--data-dir", type=Path, default=default_data_dir())
    p.add_argument("--install-config", type=Path, default=None,
                   help="Path to install_config.json. Defaults to <data-dir>/install_config.json")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--once-enroll", action="store_true",
                   help="Only enroll (if needed), write credentials, and exit. Useful for installers.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    identity_path = data_dir / "agent.json"
    install_path: Path = args.install_config or (data_dir / "install_config.json")

    # The standalone .exe ships with its config compiled in via the build
    # worker's templating step. We always prefer that over a sidecar file —
    # that's the whole point of the portable build.
    install: InstallConfig | None = InstallConfig.load_baked()
    if install is None and install_path.exists():
        install = InstallConfig.load(install_path)

    identity = AgentIdentity.load(identity_path)
    if identity is None:
        if install is None:
            log.error(
                "No agent identity and no install config (neither baked nor at %s). "
                "Provide install_config.json with the server URL and enrollment token, "
                "or rebuild the .exe via the panel's installer generator.",
                install_path,
            )
            return 2
        log.info("Enrolling with server %s", install.server_url)
        identity = enroll(install)
        identity.save(identity_path)
        log.info("Enrolled as endpoint %s", identity.endpoint_id)

    if args.once_enroll:
        return 0

    verify_tls = install.verify_tls if install is not None else True

    client = AgentClient(identity, verify_tls=verify_tls)
    try:
        asyncio.run(client.run_forever())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
