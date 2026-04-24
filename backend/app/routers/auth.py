from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record as audit
from ..database import get_db
from ..dependencies import CurrentUser
from ..models import User
from ..schemas import LoginRequest, Token, UserOut
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or user.disabled or not verify_password(payload.password, user.password_hash):
        # Log failures too so brute-force attempts show up in the audit trail.
        audit(
            db,
            action="auth.login.failed",
            target_type="user",
            target_id=payload.username,
            source_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.totp_enabled:
        import pyotp

        if not payload.totp_code or not pyotp.TOTP(user.totp_secret).verify(payload.totp_code, valid_window=1):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing TOTP code")

    token = create_access_token(str(user.id), extra={"role": user.role, "username": user.username})
    audit(
        db,
        action="auth.login.success",
        actor=user,
        source_ip=request.client.host if request.client else None,
    )
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
