from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import run_bootstrap
from .config import get_settings
from .routers import agent_ws, auth, endpoints, enrollment, ui_ws

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_bootstrap()
    yield


app = FastAPI(title="RMM", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(enrollment.admin_router)
app.include_router(enrollment.public_router)
app.include_router(endpoints.router)
app.include_router(agent_ws.router)
app.include_router(ui_ws.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": app.version}
