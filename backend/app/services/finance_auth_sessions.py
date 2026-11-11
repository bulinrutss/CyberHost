"""Sessões opacas do Financeiro (cookies financeiro_*)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.finance_auth import (
    DEVICE_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    resolve_device_id,
    set_device_cookie,
)
from app.models.finance_auth import FinanceAuthSession
from app.models.finance_user import FinanceUser
from app.services import auth_throttle


def _digest(raw: str) -> str:
    secret = get_settings().resolved_finance_secret_key.encode("utf-8")
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def access_ttl() -> timedelta:
    minutes = int(getattr(get_settings(), "auth_access_minutes", 15) or 15)
    return timedelta(minutes=max(5, min(60, minutes)))


def refresh_ttl() -> timedelta:
    hours = int(getattr(get_settings(), "auth_refresh_hours", 12) or 12)
    return timedelta(hours=max(1, min(72, hours)))


def _ua(request: Request | None) -> str:
    if request is None:
        return ""
    return (request.headers.get("user-agent") or "")[:512]


def _new_tokens() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(48)


def _cookie_secure(request: Request | None) -> bool:
    from app.auth import request_is_https

    return request_is_https(request)


def _expire_named(response: Response, name: str) -> None:
    for secure in (True, False):
        response.delete_cookie(
            key=name, path="/", httponly=True, secure=secure, samesite="lax"
        )


def set_session_cookies(
    response: Response,
    access_raw: str,
    refresh_raw: str,
    device_id: str,
    request: Request | None = None,
) -> None:
    secure = _cookie_secure(request)
    _expire_named(response, SESSION_COOKIE_NAME)
    _expire_named(response, REFRESH_COOKIE_NAME)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_raw,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_raw,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    set_device_cookie(response, device_id, request)
    response.headers["Cache-Control"] = "private, no-store"


def clear_session_cookies(response: Response, request: Request | None = None) -> None:
    del request
    _expire_named(response, SESSION_COOKIE_NAME)
    _expire_named(response, REFRESH_COOKIE_NAME)
    response.headers["Cache-Control"] = "private, no-store"


def create_session(
    db: Session,
    user: FinanceUser,
    request: Request | None,
    response: Response,
) -> FinanceAuthSession:
    device_id, _ = resolve_device_id(request)
    access_raw, refresh_raw = _new_tokens()
    now = datetime.utcnow()
    row = FinanceAuthSession(
        user_id=user.id,
        access_token_hash=_digest(access_raw),
        refresh_token_hash=_digest(refresh_raw),
        refresh_family=secrets.token_urlsafe(24),
        device_id=device_id,
        user_agent=_ua(request),
        ip=auth_throttle.client_ip(request) if request else "",
        created_at=now,
        last_seen_at=now,
        access_expires_at=now + access_ttl(),
        refresh_expires_at=now + refresh_ttl(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    set_session_cookies(response, access_raw, refresh_raw, device_id, request)
    return row


def resolve_user_from_access(
    db: Session, request: Request, access_raw: str
) -> FinanceUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
    )
    if not access_raw:
        raise credentials_exception
    row = (
        db.query(FinanceAuthSession)
        .filter(
            FinanceAuthSession.access_token_hash == _digest(access_raw),
            FinanceAuthSession.revoked_at.is_(None),
        )
        .first()
    )
    if row is None:
        raise credentials_exception
    now = datetime.utcnow()
    if row.access_expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada",
            headers={"X-Session-Expired": "1"},
        )
    cookie_did = request.cookies.get(DEVICE_COOKIE_NAME)
    if (
        not cookie_did
        or len(cookie_did) != len(row.device_id)
        or not hmac.compare_digest(row.device_id, cookie_did)
    ):
        raise credentials_exception
    user = db.get(FinanceUser, row.user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    row.last_seen_at = now
    db.commit()
    return user


def rotate_refresh(db: Session, request: Request, response: Response) -> FinanceUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
    )
    refresh_raw = request.cookies.get(REFRESH_COOKIE_NAME) or ""
    if not refresh_raw:
        raise credentials_exception
    row = (
        db.query(FinanceAuthSession)
        .filter(FinanceAuthSession.refresh_token_hash == _digest(refresh_raw))
        .first()
    )
    if row is None:
        raise credentials_exception
    now = datetime.utcnow()
    if row.revoked_at is not None:
        db.query(FinanceAuthSession).filter(
            FinanceAuthSession.refresh_family == row.refresh_family,
            FinanceAuthSession.revoked_at.is_(None),
        ).update({"revoked_at": now}, synchronize_session=False)
        db.commit()
        clear_session_cookies(response, request)
        raise credentials_exception
    if row.refresh_expires_at < now:
        row.revoked_at = now
        db.commit()
        clear_session_cookies(response, request)
        raise credentials_exception
    cookie_did = request.cookies.get(DEVICE_COOKIE_NAME)
    if (
        not cookie_did
        or len(cookie_did) != len(row.device_id)
        or not hmac.compare_digest(row.device_id, cookie_did)
    ):
        raise credentials_exception
    user = db.get(FinanceUser, row.user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    access_raw, new_refresh = _new_tokens()
    row.revoked_at = now
    replacement = FinanceAuthSession(
        user_id=user.id,
        access_token_hash=_digest(access_raw),
        refresh_token_hash=_digest(new_refresh),
        refresh_family=row.refresh_family,
        device_id=row.device_id,
        user_agent=_ua(request),
        ip=auth_throttle.client_ip(request),
        created_at=now,
        last_seen_at=now,
        access_expires_at=now + access_ttl(),
        refresh_expires_at=now + refresh_ttl(),
    )
    db.add(replacement)
    db.commit()
    set_session_cookies(response, access_raw, new_refresh, row.device_id, request)
    return user


def revoke_request_session(db: Session, request: Request) -> None:
    access_raw = request.cookies.get(SESSION_COOKIE_NAME) or ""
    refresh_raw = request.cookies.get(REFRESH_COOKIE_NAME) or ""
    now = datetime.utcnow()
    if access_raw:
        row = (
            db.query(FinanceAuthSession)
            .filter(
                FinanceAuthSession.access_token_hash == _digest(access_raw),
                FinanceAuthSession.revoked_at.is_(None),
            )
            .first()
        )
        if row is not None:
            row.revoked_at = now
    if refresh_raw:
        row = (
            db.query(FinanceAuthSession)
            .filter(
                FinanceAuthSession.refresh_token_hash == _digest(refresh_raw),
                FinanceAuthSession.revoked_at.is_(None),
            )
            .first()
        )
        if row is not None:
            row.revoked_at = now
    db.commit()
