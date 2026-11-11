"""Step-up auth: reconfirma senha (+ MFA) antes de ações sensíveis."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, verify_password
from app.config import get_settings
from app.database import get_db
from app.models.auth_security import AuthStepUpTicket
from app.models.user import User
from app.services import admin_mfa
from app.services.totp import verify_totp

STEP_UP_TTL_SECONDS = 300
_PURGE_AFTER = timedelta(hours=1)
STEP_UP_REQUIRED_HEADER = "X-Step-Up-Required"


def _digest(raw: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(AuthStepUpTicket).filter(AuthStepUpTicket.expires_at < cutoff).delete(
        synchronize_session=False
    )


def issue_step_up(
    db: Session,
    user: User,
    password: str,
    mfa_code: str | None = None,
) -> tuple[str, int]:
    if not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Senha atual incorreta",
        )
    if user.mfa_enabled:
        code = (mfa_code or "").strip()
        if not code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Código MFA obrigatório",
            )
        if not user.mfa_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA indisponível",
            )
        plain = admin_mfa.decrypt_secret(user.mfa_secret)
        if not verify_totp(plain, code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código MFA inválido",
            )

    _purge_stale(db)
    ttl = STEP_UP_TTL_SECONDS
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthStepUpTicket(
            token_hash=_digest(raw),
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        )
    )
    db.commit()
    return raw, ttl


def verify_step_up(db: Session, user_id: int, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    token = raw_token.strip()
    if not token or len(token) > 128:
        return False
    row = (
        db.query(AuthStepUpTicket)
        .filter(
            AuthStepUpTicket.token_hash == _digest(token),
            AuthStepUpTicket.user_id == user_id,
        )
        .first()
    )
    if row is None or row.expires_at <= datetime.utcnow():
        return False
    return True


def _step_up_required(user: User) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "step_up_required",
            "mfa_enabled": bool(user.mfa_enabled),
        },
        headers={STEP_UP_REQUIRED_HEADER: "1"},
    )


def require_step_up(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
) -> User:
    del request  # reservado para binding futuro (IP/UA)
    if not verify_step_up(db, user.id, x_step_up_token):
        raise _step_up_required(user)
    return user
