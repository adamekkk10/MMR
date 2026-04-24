"""Standalone CLI for the build worker — exists so you can exercise the
whole pipeline without the FastAPI/queue integration that lands next.

  python -m app.builds.cli build \\
      --server-url https://rmm.example.com \\
      --enrollment-token rmmenr_xxxxxxxxxxxx \\
      --output ./out/rmm-agent.exe \\
      --runner native

  python -m app.builds.cli template-only \\
      --server-url https://rmm.example.com \\
      --enrollment-token rmmenr_xxxxxxxxxxxx \\
      --output ./out/staged

The `template-only` subcommand is the fastest way to inspect what gets fed
into PyInstaller — it stops after writing baked.py, the .spec, and
version_info.txt.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .cache import BuildCache
from .models import BuildSpec, BuildStatus
from .templating import stage_build_tree
from .worker import PyInstallerWorker


def _common_spec_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--server-url", required=True)
    p.add_argument("--enrollment-token", required=True)
    p.add_argument("--no-verify-tls", action="store_true")
    p.add_argument("--tag", action="append", default=[], dest="tags")
    p.add_argument("--agent-version", default="0.1.0")
    p.add_argument("--icon", type=Path, default=None)
    p.add_argument("--company-name", default="RMM")
    p.add_argument("--product-name", default="RMM Agent")
    p.add_argument("--no-upx", action="store_true")
    p.add_argument("--no-strip", action="store_true")
    p.add_argument("--console", action="store_true", default=True)
    p.add_argument("--no-console", dest="console", action="store_false")
    p.add_argument("--signing-pfx", type=Path, default=None)
    p.add_argument("--signing-pfx-password", default=None)
    p.add_argument("--agent-source-dir", type=Path, default=None,
                   help="Override the path to the agent source tree (default: <repo>/agent)")


def _spec_from_args(args: argparse.Namespace) -> BuildSpec:
    kwargs: dict = dict(
        server_url=args.server_url,
        enrollment_token=args.enrollment_token,
        verify_tls=not args.no_verify_tls,
        tags=tuple(args.tags),
        agent_version=args.agent_version,
        console=args.console,
        upx=not args.no_upx,
        strip=not args.no_strip,
        icon_path=args.icon,
        company_name=args.company_name,
        product_name=args.product_name,
        signing_pfx_path=args.signing_pfx,
        signing_pfx_password=args.signing_pfx_password,
    )
    if args.agent_source_dir is not None:
        kwargs["agent_source_dir"] = args.agent_source_dir
    return BuildSpec(**kwargs)


def _cmd_build(args: argparse.Namespace) -> int:
    spec_kwargs: dict = {}
    if args.runner:
        spec_kwargs["runner"] = args.runner
    if args.docker_image:
        spec_kwargs["docker_image"] = args.docker_image

    base = _spec_from_args(args)
    spec = BuildSpec(**{**base.__dict__, **spec_kwargs})

    cache = BuildCache(args.cache_dir)
    worker = PyInstallerWorker(cache=cache, work_root=args.work_dir)
    result = worker.build(spec)

    print(f"status:   {result.status.value}")
    print(f"cache:    {result.cache_key}")
    print(f"duration: {result.duration_seconds:.1f}s")
    if result.size_bytes is not None:
        print(f"size:     {result.size_bytes / 1_048_576:.1f} MiB")
    if result.signed:
        print("signed:   yes")
    if result.status is BuildStatus.FAILED:
        print("error:    " + (result.error or "(unknown)"), file=sys.stderr)
        if result.log_tail:
            print("\n--- log tail ---", file=sys.stderr)
            print(result.log_tail, file=sys.stderr)
        return 1

    assert result.artifact_path is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(result.artifact_path, args.output)
    print(f"output:   {args.output}")
    return 0


def _cmd_template_only(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    args.output.mkdir(parents=True, exist_ok=True)
    stage_build_tree(spec, args.output)
    print(f"Staged PyInstaller workdir at {args.output}")
    print("Contents:")
    for p in sorted(args.output.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(args.output)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="rmm-builds")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Produce a .exe (runs PyInstaller).")
    _common_spec_args(p_build)
    p_build.add_argument("--output", type=Path, required=True, help="Where to drop the .exe")
    p_build.add_argument("--cache-dir", type=Path, default=Path("./var/build-cache"))
    p_build.add_argument("--work-dir", type=Path, default=Path("./var/build-work"))
    p_build.add_argument("--runner", choices=["auto", "docker", "native"], default=None)
    p_build.add_argument("--docker-image", default=None)
    p_build.set_defaults(func=_cmd_build)

    p_tpl = sub.add_parser("template-only", help="Stage the build tree without running PyInstaller.")
    _common_spec_args(p_tpl)
    p_tpl.add_argument("--output", type=Path, required=True, help="Directory to write the staged tree into")
    p_tpl.set_defaults(func=_cmd_template_only)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
