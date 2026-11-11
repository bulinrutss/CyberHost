"""Auth HTTP do Financeiro — isolado do /api/auth do CyberHost."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.finance_auth import (
    attach_finance_session,
    clear_finance_session_cookie,
    get_current_finance_user,
    hash_password,
    verify_password,
)
from app.finance_database import get_finance_db
from app.models.finance_user import FinanceUser
from app.schemas.auth import Token, UserResponse
from app.services import auth_throttle, finance_auth_sessions, finance_mfa
from app.utils.phone import normalize_phone

router = APIRouter()
LOGIN_FAILED = "Telefone, e-mail ou senha incorretos"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FinanceRegisterPayload(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class FinanceMfaVerifyPayload(BaseModel):
    ticket: str = Field(min_length=10, max_length=128)
    code: str = Field(min_length=6, max_length=16)


def _login_identifier(username: str) -> tuple[str, str]:
    raw = (username or "").strip()
    if "@" in raw:
        return "email", raw.lower()
    return "phone", normalize_phone(raw)


def _find_user(db: Session, kind: str, ident: str) -> FinanceUser | None:
    if not ident:
        return None
    if kind == "email":
        return db.query(FinanceUser).filter(FinanceUser.email == ident).first()
    return db.query(FinanceUser).filter(FinanceUser.phone == ident).first()


@router.post("/register", response_model=UserResponse)
def register(payload: FinanceRegisterPayload, db: Session = Depends(get_finance_db)):
    phone = normalize_phone(payload.phone)
    email = payload.email.strip().lower()
    if not phone or len(phone) < 10:
        raise HTTPException(status_code=400, detail="Telefone inválido")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="E-mail inválido")
    if db.query(FinanceUser).filter(FinanceUser.phone == phone).first():
        raise HTTPException(status_code=400, detail="Telefone já cadastrado")
    if db.query(FinanceUser).filter(FinanceUser.email == email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = FinanceUser(
        phone=phone,
        email=email,
        name=payload.name.strip(),
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id,
        phone=user.phone,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        is_admin=False,
        mfa_enabled=bool(user.mfa_enabled),
        created_at=user.created_at,
    )


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_finance_db),
):
    ip = auth_throttle.client_ip(request)
    kind, ident = _login_identifier(form.username)
    # Throttle usa o DB do host (compartilhado) — ok como proteção de rede.
    from app.database import SessionLocal

    host_db = SessionLocal()
    try:
        auth_throttle.raise_if_limited(
            auth_throttle.check_lock(host_db, auth_throttle.LOGIN_IP_SCOPE, ip),
            auth_throttle.check_lock(
                host_db, auth_throttle.LOGIN_PHONE_SCOPE, ident or "empty"
            ),
        )
        user = _find_user(db, kind, ident)
        from app.auth import hash_password as _hp

        hashed = user.hashed_password if user is not None else _hp("dummy-password-xx")
        valid = verify_password(form.password, hashed)
        if user is None or not user.is_active or not valid:
            auth_throttle.raise_if_limited(
                auth_throttle.add_hit(
                    host_db, auth_throttle.LOGIN_IP_SCOPE, ip, ip=ip, failed=True
                ),
                auth_throttle.add_hit(
                    host_db,
                    auth_throttle.LOGIN_PHONE_SCOPE,
                    ident or "empty",
                    ip=ip,
                    failed=True,
                ),
            )
            raise HTTPException(status_code=401, detail=LOGIN_FAILED)
        auth_throttle.reset_bucket(host_db, auth_throttle.LOGIN_PHONE_SCOPE, ident)
    finally:
        host_db.close()

    mfa = finance_mfa.start_challenge(db, user)
    if mfa is not None:
        clear_finance_session_cookie(response, request)
        return Token(**mfa)
    attach_finance_session(response, user.id, request, db=db)
    return Token(authenticated=True)


@router.post("/mfa/verify", response_model=Token)
def verify_mfa(
    payload: FinanceMfaVerifyPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_finance_db),
):
    user = finance_mfa.redeem_mfa_ticket(db, payload.ticket, payload.code)
    attach_finance_session(response, user.id, request, db=db)
    return Token(authenticated=True)


@router.get("/me", response_model=UserResponse)
def me(user: FinanceUser = Depends(get_current_finance_user)):
    return UserResponse(
        id=user.id,
        phone=user.phone,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        is_admin=False,
        mfa_enabled=bool(user.mfa_enabled),
        created_at=user.created_at,
    )


@router.post("/refresh", response_model=Token)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_finance_db),
):
    finance_auth_sessions.rotate_refresh(db, request, response)
    return Token(authenticated=True)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_finance_db),
):
    finance_auth_sessions.revoke_request_session(db, request)
    clear_finance_session_cookie(response, request)
    return {"ok": True}
