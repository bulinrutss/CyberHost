"""Rate limit e backoff de autenticação, compartilhado entre workers via banco."""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth_security import AuthThrottle

logger = logging.getLogger(__name__)

LOGIN_IP_SCOPE = "login_ip"
LOGIN_PHONE_SCOPE = "login_phone"
REGISTER_IP_SCOPE = "register_ip"
MFA_IP_SCOPE = "mfa_ip"
WHATSAPP_SEND_IP_SCOPE = "wa_send_ip"
WHATSAPP_SEND_PHONE_SCOPE = "wa_send_phone"
WHATSAPP_VERIFY_PHONE_SCOPE = "wa_verify_phone"
EMAIL_SEND_IP_SCOPE = "email_send_ip"
EMAIL_SEND_SCOPE = "email_send"
EMAIL_VERIFY_SCOPE = "email_verify"
ANALYTICS_IP_SCOPE = "analytics_ip"
WEB_ANALYTICS_IP_SCOPE = "web_analytics_ip"

_PRIVATE_PREFIXES = ("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.")
_PRIVATE_172 = tuple(f"172.{n}." for n in range(16, 32))


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    trusted = _trusted_peer(peer)
    if trusted:
        for header in ("cf-connecting-ip", "x-real-ip"):
            value = (request.headers.get(header) or "").strip()
            if _valid_ip(value):
                return value
    return peer or "0.0.0.0"


def _trusted_peer(peer: str) -> bool:
    if not peer:
        return False
    if peer in {"127.0.0.1", "::1"}:
        return True
    return peer.startswith(_PRIVATE_PREFIXES) or peer.startswith(_PRIVATE_172)


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _limits(scope: str) -> tuple[int, int]:
    settings = get_settings()
    if scope == LOGIN_IP_SCOPE:
        return (
            int(getattr(settings, "auth_login_ip_max", 20) or 20),
            int(getattr(settings, "auth_login_ip_window_seconds", 600) or 600),
        )
    if scope == LOGIN_PHONE_SCOPE:
        return (
            int(getattr(settings, "auth_login_phone_fail_max", 8) or 8),
            int(getattr(settings, "auth_login_phone_window_seconds", 900) or 900),
        )
    if scope == REGISTER_IP_SCOPE:
        return (
            int(getattr(settings, "auth_register_ip_max", 5) or 5),
            int(getattr(settings, "auth_register_ip_window_seconds", 3600) or 3600),
        )
    if scope == WHATSAPP_SEND_IP_SCOPE:
        return (
            int(getattr(settings, "whatsapp_send_ip_max", 10) or 10),
            int(getattr(settings, "whatsapp_send_ip_window_seconds", 3600) or 3600),
        )
    if scope == WHATSAPP_SEND_PHONE_SCOPE:
        return (
            int(getattr(settings, "whatsapp_send_phone_max", 5) or 5),
            int(getattr(settings, "whatsapp_send_phone_window_seconds", 3600) or 3600),
        )
    if scope == WHATSAPP_VERIFY_PHONE_SCOPE:
        return (
            int(getattr(settings, "whatsapp_verify_phone_max", 8) or 8),
            int(getattr(settings, "whatsapp_verify_phone_window_seconds", 900) or 900),
        )
    if scope == EMAIL_SEND_IP_SCOPE:
        return (
            int(getattr(settings, "email_send_ip_max", 10) or 10),
            int(getattr(settings, "email_send_ip_window_seconds", 3600) or 3600),
        )
    if scope == EMAIL_SEND_SCOPE:
        return (
            int(getattr(settings, "email_send_max", 5) or 5),
            int(getattr(settings, "email_send_window_seconds", 3600) or 3600),
        )
    if scope == EMAIL_VERIFY_SCOPE:
        return (
            int(getattr(settings, "email_verify_max", 8) or 8),
            int(getattr(settings, "email_verify_window_seconds", 900) or 900),
        )
    if scope in {ANALYTICS_IP_SCOPE, WEB_ANALYTICS_IP_SCOPE}:
        return (40, 60)
    return (
        int(getattr(settings, "auth_mfa_ip_max", 10) or 10),
        int(getattr(settings, "auth_login_ip_window_seconds", 600) or 600),
    )


def _backoff_seconds(count: int) -> int:
    if count < 3:
        return 0
    return min(2 ** (count - 2), 60)


def _alert_label(scope: str, key: str) -> str:
    if "phone" in scope:
        return f"***{key[-4:]}" if len(key) >= 4 else "***"
    return key


def _locked_retry(row: AuthThrottle, now: datetime) -> int:
    if row.locked_until and row.locked_until > now:
        return max(1, int((row.locked_until - now).total_seconds()))
    return 0


def _raise_limited(retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Muitas tentativas. Tente de novo em {retry_after}s.",
        headers={"Retry-After": str(retry_after)},
    )


def _get_row(db: Session, scope: str, key: str, now: datetime) -> AuthThrottle:
    query = db.query(AuthThrottle).filter(
        AuthThrottle.scope == scope,
        AuthThrottle.key_value == key,
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    row = query.first()
    if row is not None:
        return row
    row = AuthThrottle(
        scope=scope,
        key_value=key,
        window_started_at=now,
        count=0,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        fetched = query.first()
        if fetched is None:
            raise
        return fetched


def _refresh_window(row: AuthThrottle, window_seconds: int, now: datetime) -> None:
    if row.locked_until and row.locked_until <= now:
        row.locked_until = None
    elapsed = (now - row.window_started_at).total_seconds()
    if elapsed >= window_seconds:
        row.window_started_at = now
        row.count = 0


def check_lock(db: Session, scope: str, key: str) -> int:
    """Retorna segundos de espera se o balde estiver fechado; 0 se livre."""
    if not key:
        return 0
    now = datetime.utcnow()
    _max, window = _limits(scope)
    row = _get_row(db, scope, key, now)
    _refresh_window(row, window, now)
    retry = _locked_retry(row, now)
    db.commit()
    return retry


def add_hit(
    db: Session,
    scope: str,
    key: str,
    *,
    ip: str | None = None,
    failed: bool = True,
) -> int:
    """Incrementa o balde. Retorna Retry-After (>0) se backoff/bloqueio."""
    if not key:
        return 0
    now = datetime.utcnow()
    max_count, window = _limits(scope)
    row = _get_row(db, scope, key, now)
    _refresh_window(row, window, now)
    retry = _locked_retry(row, now)
    if retry:
        db.commit()
        return retry

    row.count += 1
    if row.count > max_count:
        row.locked_until = now + timedelta(seconds=window)
        _maybe_alert(row, scope, key, ip=ip, now=now)
        db.commit()
        return window
    backoff = _backoff_seconds(row.count) if failed else 0
    db.commit()
    return backoff


def raise_if_limited(*retries: int) -> None:
    wait = max((n for n in retries if n), default=0)
    if wait:
        _raise_limited(wait)


def reset_bucket(db: Session, scope: str, key: str) -> None:
    if not key:
        return
    row = (
        db.query(AuthThrottle)
        .filter(AuthThrottle.scope == scope, AuthThrottle.key_value == key)
        .first()
    )
    if row is None:
        return
    row.count = 0
    row.locked_until = None
    row.window_started_at = datetime.utcnow()
    db.commit()


def _maybe_alert(
    row: AuthThrottle,
    scope: str,
    key: str,
    *,
    ip: str | None,
    now: datetime,
) -> None:
    if row.last_alert_at and (now - row.last_alert_at).total_seconds() < 300:
        return
    row.last_alert_at = now
    logger.warning(
        "auth throttle lock scope=%s key=%s count=%s ip=%s",
        scope,
        _alert_label(scope, key),
        row.count,
        ip or "-",
    )
