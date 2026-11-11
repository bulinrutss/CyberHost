"""MFA TOTP do Financeiro (segredo cifrado com FINANCE_SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.finance_auth import FinanceAuthMfaTicket
from app.models.finance_user import FinanceUser
from app.services.totp import generate_secret, otpauth_url, verify_totp

logger = logging.getLogger(__name__)
PURPOSE_ENROLL = "enroll"
PURPOSE_CHALLENGE = "challenge"
_PURGE_AFTER = timedelta(hours=1)


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        f"finance-mfa:{get_settings().resolved_finance_secret_key}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA indisponível; faça login novamente para recadastrar",
        ) from exc


def _digest(raw: str) -> str:
    secret = get_settings().resolved_finance_secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def ticket_ttl_seconds() -> int:
    configured = int(getattr(get_settings(), "auth_mfa_ticket_seconds", 120) or 120)
    return max(30, min(300, configured))


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(FinanceAuthMfaTicket).filter(FinanceAuthMfaTicket.expires_at < cutoff).delete(
        synchronize_session=False
    )


def issue_mfa_ticket(
    db: Session,
    user: FinanceUser,
    purpose: str,
    pending_secret: str | None = None,
) -> tuple[str, int, str | None]:
    _purge_stale(db)
    ttl = ticket_ttl_seconds()
    raw = secrets.token_urlsafe(32)
    stored_pending = encrypt_secret(pending_secret) if pending_secret else None
    db.add(
        FinanceAuthMfaTicket(
            token_hash=_digest(raw),
            user_id=user.id,
            purpose=purpose,
            pending_secret=stored_pending,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        )
    )
    db.commit()
    otpauth = otpauth_url(pending_secret, user.phone) if pending_secret else None
    return raw, ttl, otpauth


def start_challenge(db: Session, user: FinanceUser) -> dict | None:
    """Retorna payload MFA se necessário; None = seguir para sessão."""
    if not (user.mfa_enabled and user.mfa_secret):
        return None
    try:
        decrypt_secret(user.mfa_secret)
    except HTTPException:
        user.mfa_secret = None
        user.mfa_enabled = False
        db.commit()
        return None
    ticket, _ttl, _ = issue_mfa_ticket(db, user, PURPOSE_CHALLENGE)
    return {
        "authenticated": False,
        "mfa_required": True,
        "mfa_setup_required": False,
        "mfa_ticket": ticket,
        "mfa_secret": None,
        "otpauth_url": None,
    }


def start_enroll(db: Session, user: FinanceUser) -> dict:
    secret = generate_secret()
    ticket, _ttl, otpauth = issue_mfa_ticket(
        db, user, PURPOSE_ENROLL, pending_secret=secret
    )
    return {
        "authenticated": False,
        "mfa_required": False,
        "mfa_setup_required": True,
        "mfa_ticket": ticket,
        "mfa_secret": secret,
        "otpauth_url": otpauth,
    }


def redeem_mfa_ticket(db: Session, raw: str, code: str) -> FinanceUser:
    if not raw or len(raw) > 128:
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")
    row = (
        db.query(FinanceAuthMfaTicket)
        .filter(FinanceAuthMfaTicket.token_hash == _digest(raw.strip()))
        .first()
    )
    now = datetime.utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")
    user = db.get(FinanceUser, row.user_id)
    if user is None or not user.is_active:
        row.used_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")

    if row.purpose == PURPOSE_ENROLL:
        if not row.pending_secret:
            raise HTTPException(status_code=401, detail="Ticket MFA inválido")
        plain = decrypt_secret(row.pending_secret)
        if not verify_totp(plain, code):
            raise HTTPException(status_code=401, detail="Código MFA inválido")
        user.mfa_secret = encrypt_secret(plain)
        user.mfa_enabled = True
        row.used_at = now
        db.commit()
        return user

    if row.purpose == PURPOSE_CHALLENGE:
        if not user.mfa_secret:
            raise HTTPException(status_code=401, detail="Ticket MFA inválido")
        plain = decrypt_secret(user.mfa_secret)
        if not verify_totp(plain, code):
            raise HTTPException(status_code=401, detail="Código MFA inválido")
        row.used_at = now
        db.commit()
        return user

    raise HTTPException(status_code=401, detail="Ticket MFA inválido")
