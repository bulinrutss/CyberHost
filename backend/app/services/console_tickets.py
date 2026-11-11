"""Tickets curtos de uso único para o WebSocket do console VPS."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.console_ticket import ConsoleWsTicket
from app.models.user import User

TICKET_TTL_SECONDS = 60
HOST_SHELL_INSTANCE_ID = 0
_PURGE_AFTER = timedelta(hours=1)


def ticket_ttl_seconds() -> int:
    configured = int(getattr(get_settings(), "console_ws_ticket_seconds", TICKET_TTL_SECONDS) or TICKET_TTL_SECONDS)
    return max(15, min(300, configured))


def _digest(raw: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(ConsoleWsTicket).filter(ConsoleWsTicket.expires_at < cutoff).delete(synchronize_session=False)


def issue_console_ws_ticket(db: Session, user: User, instance_id: int) -> tuple[str, int]:
    _purge_stale(db)
    ttl = ticket_ttl_seconds()
    raw = secrets.token_urlsafe(32)
    db.add(
        ConsoleWsTicket(
            token_hash=_digest(raw),
            user_id=user.id,
            instance_id=instance_id,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        )
    )
    db.commit()
    return raw, ttl


def redeem_console_ws_ticket(db: Session, raw: str, instance_id: int) -> User:
    if not raw or len(raw) > 128:
        raise HTTPException(status_code=401, detail="Ticket inválido")
    digest = _digest(raw.strip())
    query = db.query(ConsoleWsTicket).filter(ConsoleWsTicket.token_hash == digest)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    row = query.first()
    now = datetime.utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Ticket inválido")
    if row.instance_id != instance_id:
        row.used_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Ticket inválido")
    row.used_at = now
    db.commit()
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Ticket inválido")
    return user


def issue_host_shell_ticket(db: Session, user: User) -> tuple[str, int]:
    if not user.is_admin or not user.is_active:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return issue_console_ws_ticket(db, user, HOST_SHELL_INSTANCE_ID)


def redeem_host_shell_ticket(db: Session, raw: str) -> User:
    user = redeem_console_ws_ticket(db, raw, HOST_SHELL_INSTANCE_ID)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


def authenticate_host_shell_websocket(
    db: Session,
    *,
    ticket: str | None,
    jwt_query: str | None,
) -> User:
    if jwt_query:
        raise HTTPException(status_code=401, detail="Ticket inválido")
    if not ticket:
        raise HTTPException(status_code=401, detail="Ticket ausente")
    return redeem_host_shell_ticket(db, ticket)


def authenticate_console_websocket(
    db: Session,
    *,
    instance_id: int,
    ticket: str | None,
    jwt_query: str | None,
) -> User:
    """O WebSocket aceita só o ticket de uso único — JWT na query é rejeitado."""
    if jwt_query:
        raise HTTPException(status_code=401, detail="Ticket inválido")
    if not ticket:
        raise HTTPException(status_code=401, detail="Ticket ausente")
    return redeem_console_ws_ticket(db, ticket, instance_id)
