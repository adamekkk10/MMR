"""PyInstaller build worker.

Runs the actual PyInstaller invocation against a staged source tree produced
by `templating.stage_build_tree`. Two runner backends:

  - "docker"  Cross-builds Windows .exe from Linux using a Wine-based image
              (see Dockerfile.builder). The caller's repo is mounted read-only
              and PyInstaller writes into a mounted workdir. Default in prod.

  - "native"  Runs `pyinstaller` in the current environment. Only produces a
              Windows .exe when the host itself is Windows. Handy for CI on
              a Windows runner, or for local development.

An optional signing step invokes `osslsigncode` against the produced binary
if a PFX is configured — osslsigncode runs happily on Linux, so signing works
whether the build itself ran in Docker or native.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .cache import BuildCache
from .models import BuildResult, BuildSpec, BuildStatus
from .templating import stage_build_tree

log = logging.getLogger(__name__)


class BuildError(RuntimeError):
    def __init__(self, message: str, *, log_tail: str = "") -> None:
        super().__init__(message)
        self.log_tail = log_tail


class PyInstallerWorker:
    def __init__(
        self,
        *,
        cache: BuildCache,
        work_root: Path,
        build_timeout_seconds: int = 900,
    ) -> None:
        self.cache = cache
        self.work_root = work_root
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.build_timeout_seconds = build_timeout_seconds

    # ------------------------------------------------------------------ public

    def build(self, spec: BuildSpec) -> BuildResult:
        cache_key = spec.fingerprint()

        cached = self.cache.lookup(cache_key)
        if cached is not None:
            log.info("Cache hit for %s", cache_key[:12])
            return BuildResult(
                status=BuildStatus.CACHED,
                artifact_path=cached.path,
                cache_key=cache_key,
                duration_seconds=0.0,
                size_bytes=cached.size_bytes,
                built_at=cached.built_at,
            )

        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="rmm-build-", dir=self.work_root) as tmp:
            workdir = Path(tmp)
            stage_build_tree(spec, workdir)

            runner = self._select_runner(spec)
            log.info("Running PyInstaller via %s runner (cache_key=%s)", runner, cache_key[:12])
            try:
                log_tail = self._run(runner, spec, workdir)
            except BuildError as e:
                return BuildResult(
                    status=BuildStatus.FAILED,
                    artifact_path=None,
                    cache_key=cache_key,
                    duration_seconds=time.monotonic() - start,
                    log_tail=e.log_tail,
                    error=str(e),
                )

            exe = workdir / "dist" / "rmm-agent.exe"
            if not exe.is_file():
                return BuildResult(
                    status=BuildStatus.FAILED,
                    artifact_path=None,
                    cache_key=cache_key,
                    duration_seconds=time.monotonic() - start,
                    log_tail=log_tail,
                    error=f"PyInstaller completed but {exe} does not exist",
                )

            signed = False
            if spec.signing_pfx_path is not None:
                try:
                    self._sign(spec, exe)
                    signed = True
                except BuildError as e:
                    return BuildResult(
                        status=BuildStatus.FAILED,
                        artifact_path=None,
                        cache_key=cache_key,
                        duration_seconds=time.monotonic() - start,
                        log_tail=e.log_tail,
                        error=f"signing failed: {e}",
                    )

            cached = self.cache.store(
                cache_key,
                exe,
                extra_meta={
                    "agent_version": spec.agent_version,
                    "build_id": spec.build_id,
                    "signed": signed,
                    "runner": runner,
                },
            )

        return BuildResult(
            status=BuildStatus.BUILT,
            artifact_path=cached.path,
            cache_key=cache_key,
            duration_seconds=time.monotonic() - start,
            log_tail=log_tail[-8192:],
            signed=signed,
            size_bytes=cached.size_bytes,
            built_at=cached.built_at,
        )

    # --------------------------------------------------------------- internals

    def _select_runner(self, spec: BuildSpec) -> str:
        if spec.runner in ("docker", "native"):
            return spec.runner
        # auto: prefer docker if the daemon is reachable, else native
        if _docker_available():
            return "docker"
        return "native"

    def _run(self, runner: str, spec: BuildSpec, workdir: Path) -> str:
        if runner == "docker":
            return self._run_docker(spec, workdir)
        if runner == "native":
            return self._run_native(workdir)
        raise BuildError(f"unknown runner {runner!r}")

    def _run_docker(self, spec: BuildSpec, workdir: Path) -> str:
        # Inside the container, /build is the workdir. PyInstaller writes dist/ there.
        # We pass no secrets via argv — the enrollment token is already in baked.py
        # on disk at this point, so it's already available to the container anyway.
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/build",
            "-w", "/build",
            spec.docker_image,
            # The container's entrypoint is wrapped so we can pass just the spec path
            "pyinstaller", "--clean", "--noconfirm", "rmm-agent.spec",
        ]
        return _run_subprocess(cmd, timeout=self.build_timeout_seconds)

    def _run_native(self, workdir: Path) -> str:
        pyinstaller = shutil.which("pyinstaller")
        if pyinstaller is None:
            raise BuildError(
                "native runner selected but `pyinstaller` is not on PATH. "
                "Install it in this environment or switch to the docker runner."
            )
        cmd = [pyinstaller, "--clean", "--noconfirm", "rmm-agent.spec"]
        return _run_subprocess(cmd, cwd=workdir, timeout=self.build_timeout_seconds)

    def _sign(self, spec: BuildSpec, exe: Path) -> None:
        osslsigncode = shutil.which("osslsigncode")
        if osslsigncode is None:
            raise BuildError("signing requested but `osslsigncode` is not on PATH")
        assert spec.signing_pfx_path is not None
        signed = exe.with_suffix(".signed.exe")
        cmd = [
            osslsigncode, "sign",
            "-pkcs12", str(spec.signing_pfx_path),
            "-n", spec.product_name,
            "-i", spec.server_url,  # Comment URL shown by Windows — same origin the agent talks to
            "-t", spec.signing_timestamp_url,
            "-in", str(exe),
            "-out", str(signed),
        ]
        env = os.environ.copy()
        if spec.signing_pfx_password:
            cmd[2:2] = ["-pass", spec.signing_pfx_password]
        _run_subprocess(cmd, timeout=120, env=env)
        signed.replace(exe)


# ----------------------------------------------------------------- helpers

def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=5, check=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def _run_subprocess(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    env: dict | None = None,
) -> str:
    log.debug("exec: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise BuildError(f"timed out after {timeout}s", log_tail=(e.stdout or b"").decode("utf-8", "replace")[-8192:]) from e

    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    combined = f"{stdout}\n---STDERR---\n{stderr}"
    if proc.returncode != 0:
        raise BuildError(
            f"{cmd[0]} exited with status {proc.returncode}",
            log_tail=combined[-8192:],
        )
    return combined
