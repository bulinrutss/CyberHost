"""Desafio OTP de telefone (hash no banco, entrega via WhatsApp)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth_security import AuthPhoneChallenge
from app.models.user import User
from app.services import whatsapp
from app.utils.phone import validate_phone

logger = logging.getLogger(__name__)

PURPOSE_REGISTER = "register"
PURPOSE_PROFILE = "profile"
_PURGE_AFTER = timedelta(hours=6)
_MAX_ATTEMPTS = 8


def verification_required() -> bool:
    return whatsapp.verification_required()


def _digest(raw: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_otp(digits: int = 6) -> str:
    span = 10 ** digits
    return f"{secrets.randbelow(span):0{digits}d}"


def _ttl_seconds() -> int:
    configured = int(getattr(get_settings(), "whatsapp_otp_ttl_seconds", 600) or 600)
    return max(60, min(900, configured))


def _resend_seconds() -> int:
    configured = int(getattr(get_settings(), "whatsapp_resend_seconds", 60) or 60)
    return max(15, min(300, configured))


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(AuthPhoneChallenge).filter(AuthPhoneChallenge.expires_at < cutoff).delete(
        synchronize_session=False
    )


def _expire_open(db: Session, phone: str, purpose: str) -> None:
    now = datetime.utcnow()
    db.query(AuthPhoneChallenge).filter(
        AuthPhoneChallenge.phone == phone,
        AuthPhoneChallenge.purpose == purpose,
        AuthPhoneChallenge.used_at.is_(None),
        AuthPhoneChallenge.expires_at > now,
    ).update({AuthPhoneChallenge.expires_at: now}, synchronize_session=False)


def _latest_sent(db: Session, phone: str, purpose: str) -> AuthPhoneChallenge | None:
    return (
        db.query(AuthPhoneChallenge)
        .filter(
            AuthPhoneChallenge.phone == phone,
            AuthPhoneChallenge.purpose == purpose,
        )
        .order_by(AuthPhoneChallenge.last_sent_at.desc())
        .first()
    )


def issue_challenge(
    db: Session,
    *,
    phone: str,
    purpose: str,
    exclude_user_id: int | None = None,
) -> tuple[str, int, int]:
    if purpose not in {PURPOSE_REGISTER, PURPOSE_PROFILE}:
        raise HTTPException(status_code=400, detail="Pedido inválido")
    if not verification_required():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Confirmação por WhatsApp indisponível",
        )

    normalized = validate_phone(phone)
    taken = db.query(User).filter(User.phone == normalized)
    if exclude_user_id is not None:
        taken = taken.filter(User.id != exclude_user_id)
    if taken.first() is not None:
        raise HTTPException(status_code=400, detail="Telefone já cadastrado")

    _purge_stale(db)
    now = datetime.utcnow()
    cooldown = _resend_seconds()
    previous = _latest_sent(db, normalized, purpose)
    if previous is not None:
        elapsed = (now - previous.last_sent_at).total_seconds()
        if elapsed < cooldown:
            wait = max(1, int(cooldown - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Aguarde {wait}s para reenviar o código.",
                headers={"Retry-After": str(wait)},
            )

    code = generate_otp(6)
    raw = secrets.token_urlsafe(32)
    ttl = _ttl_seconds()
    _expire_open(db, normalized, purpose)
    db.add(
        AuthPhoneChallenge(
            token_hash=_digest(raw),
            phone=normalized,
            purpose=purpose,
            code_hash=_digest(code),
            expires_at=now + timedelta(seconds=ttl),
            last_sent_at=now,
            attempt_count=0,
        )
    )
    db.flush()
    try:
        whatsapp.send_authentication_code(normalized, code)
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    logger.info("whatsapp otp issued purpose=%s phone=%s", purpose, f"***{normalized[-4:]}")
    return raw, ttl, cooldown


def consume_challenge(
    db: Session,
    *,
    ticket: str,
    code: str,
    phone: str,
    purpose: str,
) -> None:
    if not verification_required():
        return
    if not ticket or not code:
        raise HTTPException(
            status_code=400,
            detail="Confirme o telefone com o código enviado no WhatsApp",
        )

    normalized = validate_phone(phone)
    digits = "".join(ch for ch in code if ch.isdigit())
    now = datetime.utcnow()
    row = (
        db.query(AuthPhoneChallenge)
        .filter(AuthPhoneChallenge.token_hash == _digest(ticket))
        .first()
    )
    if (
        row is None
        or row.used_at is not None
        or row.expires_at <= now
        or row.purpose != purpose
        or row.phone != normalized
    ):
        raise HTTPException(
            status_code=400,
            detail="Código inválido ou expirado. Solicite um novo.",
        )
    if row.attempt_count >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Solicite um novo código.",
        )

    row.attempt_count += 1
    if not hmac.compare_digest(row.code_hash, _digest(digits)):
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Código inválido ou expirado. Solicite um novo.",
        )
    row.used_at = now
    db.commit()
