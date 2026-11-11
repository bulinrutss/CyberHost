from datetime import datetime, timedelta, timezone
import hmac
import re
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"
# Bearer JWT de scripts (não é a sessão do painel).
ACCESS_TOKEN_EXPIRE_MINUTES = 4 * 60
SESSION_COOKIE_NAME = "cyberhost_sid"
REFRESH_COOKIE_NAME = "cyberhost_rt"
DEVICE_COOKIE_NAME = "cyberhost_did"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, device_id: str | None = None) -> str:
    """JWT só para Bearer/scripts. O painel usa sessão opaca no banco."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {"sub": str(user_id), "exp": expire}
    if device_id:
        payload["did"] = device_id
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def request_is_https(request: Request | None) -> bool:
    if request is None:
        return False
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    visitor = (request.headers.get("cf-visitor") or "").replace(" ", "").lower()
    if '"scheme":"https"' in visitor:
        return True
    return request.url.scheme == "https"


def _cookie_secure(request: Request | None = None) -> bool:
    return request_is_https(request)


def _valid_device_id(value: str | None) -> bool:
    return bool(value and _DEVICE_ID_RE.fullmatch(value))


def resolve_device_id(request: Request | None) -> tuple[str, bool]:
    existing = request.cookies.get(DEVICE_COOKIE_NAME) if request is not None else None
    if _valid_device_id(existing):
        return existing, False  # type: ignore[return-value]
    return secrets.token_urlsafe(32), True


def _expire_named_cookie_variants(response: Response, name: str) -> None:
    for secure in (True, False):
        response.delete_cookie(
            key=name,
            path="/",
            httponly=True,
            secure=secure,
            samesite="lax",
        )


def _expire_session_cookie_variants(response: Response) -> None:
    for name in (SESSION_COOKIE_NAME, "cyberhost_session"):
        _expire_named_cookie_variants(response, name)


def set_device_cookie(response: Response, device_id: str, request: Request | None = None) -> None:
    _expire_named_cookie_variants(response, DEVICE_COOKIE_NAME)
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=device_id,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, request: Request | None = None) -> None:
    from app.services.auth_sessions import clear_session_cookies

    clear_session_cookies(response, request)


def attach_session(
    response: Response,
    user_id: int,
    request: Request | None = None,
    db: Session | None = None,
) -> None:
    from app.services.auth_sessions import create_session

    if db is None:
        raise RuntimeError("attach_session requer Session do banco")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    create_session(db, user, request, response)


def _user_from_jwt(
    token: str,
    db: Session,
    *,
    request: Request | None = None,
    require_device: bool = False,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        device_claim = payload.get("did")
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    if require_device or device_claim:
        cookie_did = request.cookies.get(DEVICE_COOKIE_NAME) if request is not None else None
        if (
            not _valid_device_id(device_claim)
            or not _valid_device_id(cookie_did)
            or not hmac.compare_digest(str(device_claim), str(cookie_did))
        ):
            raise credentials_exception

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    from app.services.auth_sessions import resolve_user_from_access

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        # Sessão opaca do painel (com device bind).
        return resolve_user_from_access(db, request, cookie_token)
    if creds is not None and creds.credentials:
        return _user_from_jwt(creds.credentials, db, request=request, require_device=False)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    try:
        return get_current_user(request=request, creds=creds, db=db)
    except HTTPException:
        return None


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return user


def get_user_from_token_string(token: str, db: Session) -> User:
    return _user_from_jwt(token, db, require_device=False)
