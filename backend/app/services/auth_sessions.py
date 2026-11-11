"""Sessões opacas no banco: access curto + refresh rotativo e revogável."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import (
    DEVICE_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    _cookie_secure,
    _expire_named_cookie_variants,
    _expire_session_cookie_variants,
    resolve_device_id,
    set_device_cookie,
)
from app.config import get_settings
from app.models.auth_security import AuthSession
from app.models.user import User
from app.services import auth_throttle


def _digest(raw: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
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


def set_session_cookies(
    response: Response,
    access_raw: str,
    refresh_raw: str,
    device_id: str,
    request: Request | None = None,
) -> None:
    secure = _cookie_secure(request)
    _expire_session_cookie_variants(response)
    _expire_named_cookie_variants(response, REFRESH_COOKIE_NAME)
    # Cookies de sessão do navegador (sem Max-Age): fechar o browser encerra.
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
    _expire_session_cookie_variants(response)
    _expire_named_cookie_variants(response, REFRESH_COOKIE_NAME)
    response.headers["Cache-Control"] = "private, no-store"


def create_session(
    db: Session,
    user: User,
    request: Request | None,
    response: Response,
) -> AuthSession:
    device_id, _ = resolve_device_id(request)
    access_raw, refresh_raw = _new_tokens()
    now = datetime.utcnow()
    row = AuthSession(
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


def _active_by_access(db: Session, access_raw: str) -> AuthSession | None:
    if not access_raw:
        return None
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.access_token_hash == _digest(access_raw),
            AuthSession.revoked_at.is_(None),
        )
        .first()
    )
    return row


def resolve_user_from_access(
    db: Session,
    request: Request,
    access_raw: str,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    row = _active_by_access(db, access_raw)
    if row is None:
        raise credentials_exception
    now = datetime.utcnow()
    if row.access_expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada",
            headers={"WWW-Authenticate": "Bearer", "X-Session-Expired": "1"},
        )
    cookie_did = request.cookies.get(DEVICE_COOKIE_NAME)
    if (
        not cookie_did
        or len(cookie_did) != len(row.device_id)
        or not hmac.compare_digest(row.device_id, cookie_did)
    ):
        raise credentials_exception
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    row.last_seen_at = now
    db.commit()
    return user


def rotate_refresh(
    db: Session,
    request: Request,
    response: Response,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
    )
    refresh_raw = request.cookies.get(REFRESH_COOKIE_NAME) or ""
    if not refresh_raw:
        raise credentials_exception
    row = (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == _digest(refresh_raw))
        .first()
    )
    if row is None:
        raise credentials_exception
    now = datetime.utcnow()
    if row.revoked_at is not None:
        # Reuso de refresh já rotacionado: invalida a família inteira.
        db.query(AuthSession).filter(
            AuthSession.refresh_family == row.refresh_family,
            AuthSession.revoked_at.is_(None),
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
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    access_raw, new_refresh = _new_tokens()
    row.revoked_at = now
    replacement = AuthSession(
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
        row = _active_by_access(db, access_raw)
        if row is not None:
            row.revoked_at = now
    if refresh_raw:
        row = (
            db.query(AuthSession)
            .filter(
                AuthSession.refresh_token_hash == _digest(refresh_raw),
                AuthSession.revoked_at.is_(None),
            )
            .first()
        )
        if row is not None:
            row.revoked_at = now
    db.commit()


def list_sessions(db: Session, user_id: int, request: Request) -> list[dict]:
    access_raw = request.cookies.get(SESSION_COOKIE_NAME) or ""
    current_hash = _digest(access_raw) if access_raw else ""
    rows = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.refresh_expires_at >= datetime.utcnow(),
        )
        .order_by(AuthSession.last_seen_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": row.id,
            "device_id": row.device_id[:12] + "…",
            "user_agent": row.user_agent,
            "ip": row.ip,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "current": row.access_token_hash == current_hash,
        }
        for row in rows
    ]


def revoke_session(db: Session, user_id: int, session_id: int) -> None:
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()


def revoke_all_sessions(db: Session, user_id: int, *, keep_current: Request | None = None) -> int:
    keep_hash = ""
    if keep_current is not None:
        access_raw = keep_current.cookies.get(SESSION_COOKIE_NAME) or ""
        if access_raw:
            keep_hash = _digest(access_raw)
    q = db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    )
    now = datetime.utcnow()
    count = 0
    for row in q.all():
        if keep_hash and row.access_token_hash == keep_hash:
            continue
        row.revoked_at = now
        count += 1
    db.commit()
    return count
