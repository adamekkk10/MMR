"""On-disk cache for built .exe artifacts.

Keyed on the deterministic fingerprint of a BuildSpec — same inputs always
yield the same cache path, so regenerating the same installer returns
immediately without re-running PyInstaller. Cache entries are just files;
no database, no concurrency primitives beyond atomic rename on write.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CachedArtifact:
    path: Path
    size_bytes: int
    built_at: datetime
    cache_key: str


class BuildCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir_for(self, cache_key: str) -> Path:
        # Shard by first 2 hex chars to keep directory sizes sane at scale
        return self.root / cache_key[:2] / cache_key

    def lookup(self, cache_key: str) -> CachedArtifact | None:
        d = self._dir_for(cache_key)
        exe = d / "rmm-agent.exe"
        meta = d / "meta.json"
        if not (exe.is_file() and meta.is_file()):
            return None
        try:
            data = json.loads(meta.read_text())
            return CachedArtifact(
                path=exe,
                size_bytes=exe.stat().st_size,
                built_at=datetime.fromisoformat(data["built_at"]),
                cache_key=cache_key,
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            # Corrupt cache entry — nuke it so the next build rewrites cleanly
            shutil.rmtree(d, ignore_errors=True)
            return None

    def store(self, cache_key: str, built_exe: Path, *, extra_meta: dict | None = None) -> CachedArtifact:
        """Atomically promote a freshly-built .exe into the cache."""
        if not built_exe.is_file():
            raise FileNotFoundError(built_exe)

        final_dir = self._dir_for(cache_key)
        final_dir.parent.mkdir(parents=True, exist_ok=True)

        # Write into a sibling staging dir, then rename. POSIX rename of a dir over
        # an existing (empty) target isn't atomic in the general case, so if the
        # final dir already exists (two workers racing) we keep the existing one.
        with tempfile.TemporaryDirectory(prefix=".tmp-", dir=final_dir.parent) as tmp:
            staged_dir = Path(tmp) / "entry"
            staged_dir.mkdir()
            staged_exe = staged_dir / "rmm-agent.exe"
            shutil.copy2(built_exe, staged_exe)
            meta = {
                "cache_key": cache_key,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "size_bytes": staged_exe.stat().st_size,
                **(extra_meta or {}),
            }
            (staged_dir / "meta.json").write_text(json.dumps(meta, indent=2))

            try:
                os.rename(staged_dir, final_dir)
            except OSError:
                # Loser of the race — another worker already populated it.
                # That artifact is equivalent (same cache_key = same inputs), so use it.
                pass

        cached = self.lookup(cache_key)
        if cached is None:
            raise RuntimeError(f"cache entry {cache_key} missing after store")
        return cached

    def evict(self, cache_key: str) -> bool:
        d = self._dir_for(cache_key)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True
