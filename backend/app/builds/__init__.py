"""Server-side installer build worker.

Produces portable standalone .exe artifacts for the Python RMM agent using
PyInstaller onefile mode. The template step here injects the server URL +
enrollment token into a generated `baked.py` module inside a temp copy of
the agent source tree; PyInstaller then packages that tree into a single exe.

Public API surface:
  - models.BuildSpec / BuildResult / BuildStatus
  - templating.render_baked_module / render_spec_file / render_version_info
  - cache.BuildCache
  - worker.PyInstallerWorker

The worker is deliberately independent of FastAPI — it can be driven from an
API handler, a background task runner, or the standalone CLI in cli.py. Wiring
into the panel's build queue + audit log happens in a follow-up commit.
"""
