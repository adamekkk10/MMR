# RMM

Self-hosted, web-based Remote Monitoring & Management for your own fleet. A modern
alternative to Tactical RMM / MeshCentral, built for homelabs, family machines
you support with consent, and small business endpoints with consent.

**Design constraints:**

- Transparent agent — visible service name, no hidden processes, user-visible tray
  (coming in phase 2) on desktop sessions.
- Outbound-only — agents initiate a WebSocket to the server; no inbound ports on
  endpoints.
- Auditable — every panel action is recorded server-side, append-only.
- Self-hosted, no phone-home, no third-party telemetry.
- TLS everywhere in production; secrets encrypted at rest.

## Stack

| Layer    | Tech                                          |
| -------- | --------------------------------------------- |
| Backend  | Python 3.12 · FastAPI · SQLAlchemy 2          |
| DB       | PostgreSQL 16                                 |
| Frontend | React 18 · TypeScript · Tailwind · Vite       |
| Agent    | Python 3 · psutil · websockets (PyInstaller)  |
| Transport| WebSocket over TLS, JWT for UI, bearer token for agents |

## Quick start (local)

```bash
cp .env.example .env
# edit .env: set RMM_SECRET_KEY to a long random string
docker compose up --build
```

- Panel: http://localhost:8080
- API:   http://localhost:8000 (OpenAPI at `/docs`)
- Default login: `admin` / `admin` (change immediately via the bootstrap env vars, then sign in and rotate)

### Enrolling your first agent

1. Sign into the panel as `admin`.
2. `POST /api/v1/enrollment-tokens` (Swagger UI works) to mint an enrollment token.
   A UI for this is next on the roadmap.
3. On the endpoint, create `install_config.json`:
   ```json
   {
     "server_url": "http://<your-server>:8000",
     "enrollment_token": "rmmenr_xxxxxxxx",
     "verify_tls": false
   }
   ```
   Put it at `/var/lib/rmm-agent/install_config.json` (Linux) or
   `%PROGRAMDATA%\RMM Agent\install_config.json` (Windows).
4. Install deps and run:
   ```bash
   cd agent
   pip install -r requirements.txt
   python -m rmm_agent
   ```
5. The endpoint appears in the dashboard within ~15 seconds. Live CPU/memory/disk
   bars update via WebSocket.

`verify_tls` **must** be `true` in any non-local deployment. `http://` is only
acceptable on localhost/lab networks.

## Repo layout

```
backend/        FastAPI server
  app/
    main.py              app factory, lifespan, router mounts
    config.py            pydantic-settings
    database.py          engine + SessionLocal
    models.py            SQLAlchemy models
    schemas.py           Pydantic I/O schemas
    security.py          password hashing, JWT, agent-token HMAC
    dependencies.py      current-user + RBAC deps
    audit.py             audit-log writer
    websocket_manager.py live agent + UI connection registry
    bootstrap.py         create_all + bootstrap admin
    routers/
      auth.py            /auth/login, /auth/me
      enrollment.py      /enrollment-tokens (admin), /agents/enroll (public)
      endpoints.py       /endpoints CRUD
      agent_ws.py        /agents/ws    (agent transport)
      ui_ws.py           /ws           (dashboard transport)
agent/          Python agent
  rmm_agent/
    __main__.py   entrypoint + CLI
    config.py     install_config.json and agent.json persistence
    enrollment.py one-shot enrollment via HTTPS
    client.py     async WebSocket client with reconnect
    metrics.py    psutil heartbeat collection
frontend/       React + Vite + Tailwind dashboard
docker-compose.yml
```

## Roadmap

The MVP foundation here covers the first four items from the master plan:

- [x] Project structure + Docker Compose
- [x] FastAPI skeleton with agent + UI WebSocket endpoints
- [x] Agent registration, heartbeat, online/offline status
- [x] Dashboard with live CPU/memory/disk

Next up (in order):

1. **Remote shell** — bidirectional PTY streamed over WebSocket, with asciinema-
   format recording written to `recordings/<endpoint_id>/<session_id>.cast` for
   audit replay. Surface in the UI as a terminal component.
2. **File transfer** — chunked upload/download over the existing WebSocket
   (server initiates a transfer command, agent responds with chunks).
3. **Installer generator** — endpoint `/api/v1/installers?os=linux|windows` that
   bakes the server URL + a freshly-minted single-use enrollment token into a
   `.sh` / `.msi` / `.deb`. Builds use PyInstaller in the backend image.
4. **Saved scripts + bulk actions + scheduled tasks** — scripts table, fan-out
   executor, cron scheduler (APScheduler).
5. **Secrets vault** — Fernet-encrypted rows keyed by an app-level master key
   (read from `RMM_VAULT_KEY`, separate from `RMM_SECRET_KEY`). Injected into
   scripts as environment variables at exec time, never logged.
6. **RBAC hardening** — `require_admin` / `require_operator` are in place; expand
   to per-endpoint ACLs before opening this up to anything beyond trusted ops.
7. **TOTP 2FA enrollment UI** — server-side support is already wired into the
   `User` model and `/auth/login`.
8. **Alerting** — email + Discord webhook delivery on CPU/disk/offline triggers.

## Security posture (MVP caveats)

- Agent auth is a long-lived bearer token HMAC'd with the server secret. Good
  enough for a lab; plan to upgrade to mTLS with per-endpoint certs issued at
  enrollment before exposing this to the public internet.
- The server secret (`RMM_SECRET_KEY`) is used for JWT signing **and** agent
  token hashing. Rotating it invalidates both — intentional for now, revisit
  when we split them.
- Schema changes are applied via `Base.metadata.create_all` on startup. Before
  the first real deployment, switch to Alembic so we can evolve safely.
- No rate limiting on `/auth/login` yet. Put the panel behind a reverse proxy
  with rate limits (nginx `limit_req`, Caddy `rate_limit`, etc.) until we add
  per-account lockout.
- The `install_config.json` format does not include a server cert fingerprint
  yet. Add one (TOFU pinning) before shipping installers over untrusted networks.

## Development without Docker

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# point at a local postgres (see .env)
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Agent:

```bash
cd agent
pip install -r requirements.txt
python -m rmm_agent --data-dir ./data
```
