"""Auth do Financeiro: cookies e sessões isolados do CyberHost."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.auth import hash_password, request_is_https, verify_password
from app.config import get_settings
from app.finance_database import get_finance_db
from app.models.finance_user import FinanceUser

ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "financeiro_sid"
REFRESH_COOKIE_NAME = "financeiro_rt"
DEVICE_COOKIE_NAME = "financeiro_did"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
bearer_scheme = HTTPBearer(auto_error=False)


def finance_secret() -> str:
    return get_settings().resolved_finance_secret_key


def _cookie_secure(request: Request | None = None) -> bool:
    return request_is_https(request)


def _valid_device_id(value: str | None) -> bool:
    return bool(value and _DEVICE_ID_RE.fullmatch(value))


def resolve_device_id(request: Request | None) -> tuple[str, bool]:
    existing = request.cookies.get(DEVICE_COOKIE_NAME) if request is not None else None
    if _valid_device_id(existing):
        return existing, False  # type: ignore[return-value]
    return secrets.token_urlsafe(32), True


def _expire_named(response: Response, name: str) -> None:
    for secure in (True, False):
        response.delete_cookie(
            key=name, path="/", httponly=True, secure=secure, samesite="lax"
        )


def set_device_cookie(response: Response, device_id: str, request: Request | None = None) -> None:
    _expire_named(response, DEVICE_COOKIE_NAME)
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=device_id,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def create_finance_access_token(user_id: int) -> str:
    """JWT Bearer só para testes/scripts do Financeiro."""
    expire = datetime.now(timezone.utc) + timedelta(hours=4)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "aud": "financeiro"},
        finance_secret(),
        algorithm=ALGORITHM,
    )


def attach_finance_session(
    response: Response,
    user_id: int,
    request: Request | None,
    db: Session,
) -> None:
    from app.services import finance_auth_sessions

    user = db.get(FinanceUser, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    finance_auth_sessions.create_session(db, user, request, response)


def clear_finance_session_cookie(response: Response, request: Request | None = None) -> None:
    from app.services import finance_auth_sessions

    finance_auth_sessions.clear_session_cookies(response, request)


def get_current_finance_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_finance_db),
) -> FinanceUser:
    from app.services import finance_auth_sessions

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return finance_auth_sessions.resolve_user_from_access(db, request, cookie_token)
    if creds is not None and creds.credentials:
        try:
            payload = jwt.decode(
                creds.credentials,
                finance_secret(),
                algorithms=[ALGORITHM],
                audience="financeiro",
            )
            user_id = payload.get("sub")
            if user_id is None:
                raise InvalidTokenError("missing sub")
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciais inválidas",
            ) from exc
        user = db.get(FinanceUser, int(user_id))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
    )


__all__ = [
    "SESSION_COOKIE_NAME",
    "REFRESH_COOKIE_NAME",
    "DEVICE_COOKIE_NAME",
    "attach_finance_session",
    "clear_finance_session_cookie",
    "create_finance_access_token",
    "finance_secret",
    "get_current_finance_user",
    "hash_password",
    "resolve_device_id",
    "set_device_cookie",
    "verify_password",
]
