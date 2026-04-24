from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()

_pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")


# --- Password hashing ---

def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_ctx.verify(password, password_hash)
    except Exception:
        return False


# --- JWT (user/web sessions) ---

def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError(str(e)) from e


# --- Agent tokens ---
#
# Generated at enrollment, stored as a salted hash server-side. The plaintext only
# lives in the agent's config file on disk. If an agent is compromised the admin
# revokes the Endpoint row (or we'll add a dedicated revocation flag) and issues
# a new enrollment token.

_AGENT_TOKEN_BYTES = 32


def generate_agent_token() -> str:
    # URL-safe so it drops cleanly into installer configs
    return "rmmagt_" + secrets.token_urlsafe(_AGENT_TOKEN_BYTES)


def hash_agent_token(token: str) -> str:
    # Deterministic HMAC so we can look up by hash. The pepper is the server secret,
    # which is required to recover any candidate hash from a stolen DB dump.
    digest = hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def verify_agent_token(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_agent_token(token), stored_hash)


# --- Enrollment tokens ---

def generate_enrollment_token() -> str:
    return "rmmenr_" + secrets.token_urlsafe(24)
