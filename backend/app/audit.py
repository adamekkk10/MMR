from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog, User


def record(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    source_ip: str | None = None,
) -> None:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        source_ip=source_ip,
    )
    db.add(entry)
    db.commit()
