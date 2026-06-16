"""One-shot startup tasks: create tables if missing, seed the bootstrap admin user."""
from __future__ import annotations

import logging

from sqlalchemy import select

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import User
from .security import hash_password

log = logging.getLogger(__name__)


def run_bootstrap() -> None:
    # For MVP we create tables directly. A follow-up will switch to Alembic migrations.
    Base.metadata.create_all(bind=engine)

    settings = get_settings()
    if not (settings.bootstrap_admin_username and settings.bootstrap_admin_password):
        return

    with SessionLocal() as db:
        existing = db.scalar(select(User).limit(1))
        if existing is not None:
            return
        admin = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        log.warning(
            "Created bootstrap admin user %r. CHANGE THE PASSWORD IMMEDIATELY.",
            settings.bootstrap_admin_username,
        )
