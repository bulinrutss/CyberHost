"""MFA TOTP para administradores: ticket de uso único e segredo cifrado."""

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
from app.models.auth_security import AuthMfaTicket
from app.models.user import User
from app.services.totp import generate_secret, otpauth_url, verify_totp

logger = logging.getLogger(__name__)
PURPOSE_ENROLL = "enroll"
PURPOSE_CHALLENGE = "challenge"
_PURGE_AFTER = timedelta(hours=1)


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"mfa:{get_settings().secret_key}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA indisponível; peça reset a outro administrador",
        ) from exc


def _digest(raw: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def required() -> bool:
    return bool(getattr(get_settings(), "admin_mfa_required", False))


def ticket_ttl_seconds() -> int:
    configured = int(getattr(get_settings(), "auth_mfa_ticket_seconds", 120) or 120)
    return max(30, min(300, configured))


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(AuthMfaTicket).filter(AuthMfaTicket.expires_at < cutoff).delete(
        synchronize_session=False
    )


def issue_mfa_ticket(
    db: Session,
    user: User,
    purpose: str,
    pending_secret: str | None = None,
) -> tuple[str, int, str | None]:
    _purge_stale(db)
    ttl = ticket_ttl_seconds()
    raw = secrets.token_urlsafe(32)
    stored_pending = encrypt_secret(pending_secret) if pending_secret else None
    db.add(
        AuthMfaTicket(
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


def _secret_readable(token: str | None) -> bool:
    if not token:
        return False
    try:
        decrypt_secret(token)
        return True
    except HTTPException:
        return False


def start_admin_login(db: Session, user: User) -> dict:
    """Após senha válida, quando ADMIN_MFA_REQUIRED=true: JWT só depois do TOTP."""
    if user.mfa_enabled and user.mfa_secret and _secret_readable(user.mfa_secret):
        ticket, _ttl, _ = issue_mfa_ticket(db, user, PURPOSE_CHALLENGE)
        return {
            "access_token": "",
            "token_type": "bearer",
            "authenticated": False,
            "mfa_required": True,
            "mfa_setup_required": False,
            "mfa_ticket": ticket,
            "mfa_secret": None,
            "otpauth_url": None,
        }

    if user.mfa_enabled or user.mfa_secret:
        # Ex.: SECRET_KEY rotacionado — segredo antigo ilegível; força novo enrolamento.
        logger.warning(
            "MFA admin ilegível; forçando recadastro user_id=%s",
            user.id,
        )
        clear_mfa(user)
        db.commit()

    secret = generate_secret()
    ticket, _ttl, otpauth = issue_mfa_ticket(db, user, PURPOSE_ENROLL, pending_secret=secret)
    logger.info("MFA setup iniciado para admin id=%s", user.id)
    return {
        "access_token": "",
        "token_type": "bearer",
        "authenticated": False,
        "mfa_required": False,
        "mfa_setup_required": True,
        "mfa_ticket": ticket,
        "mfa_secret": secret,
        "otpauth_url": otpauth,
    }


def redeem_mfa_ticket(
    db: Session,
    raw: str,
    code: str,
    *,
    expected_user_id: int | None = None,
) -> User:
    if not raw or len(raw) > 128:
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")
    digest = _digest(raw.strip())
    query = db.query(AuthMfaTicket).filter(AuthMfaTicket.token_hash == digest)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    row = query.first()
    now = datetime.utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")
    if expected_user_id is not None and row.user_id != expected_user_id:
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        row.used_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Ticket MFA inválido")

    if row.purpose == PURPOSE_ENROLL:
        if not row.pending_secret:
            row.used_at = now
            db.commit()
            raise HTTPException(status_code=401, detail="Ticket MFA inválido")
        plain = decrypt_secret(row.pending_secret)
        if not verify_totp(plain, code):
            raise HTTPException(status_code=401, detail="Código MFA inválido")
        user.mfa_secret = encrypt_secret(plain)
        user.mfa_enabled = True
        row.used_at = now
        db.commit()
        logger.info("MFA ativado para admin id=%s", user.id)
        return user

    if row.purpose == PURPOSE_CHALLENGE:
        if not user.mfa_secret:
            row.used_at = now
            db.commit()
            raise HTTPException(status_code=401, detail="Ticket MFA inválido")
        plain = decrypt_secret(user.mfa_secret)
        if not verify_totp(plain, code):
            raise HTTPException(status_code=401, detail="Código MFA inválido")
        row.used_at = now
        db.commit()
        return user

    row.used_at = now
    db.commit()
    raise HTTPException(status_code=401, detail="Ticket MFA inválido")


def clear_mfa(user: User) -> None:
    user.mfa_secret = None
    user.mfa_enabled = False
