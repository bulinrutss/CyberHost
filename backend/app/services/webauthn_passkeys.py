"""Passkeys / WebAuthn: registro, login, listagem e exclusão."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_settings
from app.models.auth_security import AuthWebAuthnChallenge, WebAuthnCredential
from app.models.user import User
from app.utils.phone import normalize_phone

PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"
_CHALLENGE_TTL = timedelta(minutes=5)
_PURGE_AFTER = timedelta(hours=1)


def rp_id() -> str:
    settings = get_settings()
    configured = (settings.webauthn_rp_id or "").strip()
    if configured:
        return configured
    host = urlparse(settings.resolved_frontend_url).hostname
    return host or "localhost"


def rp_origin() -> str:
    settings = get_settings()
    configured = (settings.webauthn_origin or "").strip().rstrip("/")
    if configured:
        return configured
    parsed = urlparse(settings.resolved_frontend_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:3000"


def rp_name() -> str:
    return (get_settings().webauthn_rp_name or "CyberHost").strip() or "CyberHost"


def _purge_stale(db: Session) -> None:
    cutoff = datetime.utcnow() - _PURGE_AFTER
    db.query(AuthWebAuthnChallenge).filter(
        AuthWebAuthnChallenge.expires_at < cutoff
    ).delete(synchronize_session=False)


def _store_challenge(
    db: Session,
    *,
    challenge_b64: str,
    user_id: int | None,
    purpose: str,
) -> None:
    _purge_stale(db)
    db.add(
        AuthWebAuthnChallenge(
            challenge=challenge_b64[:128],
            user_id=user_id,
            purpose=purpose,
            expires_at=datetime.utcnow() + _CHALLENGE_TTL,
        )
    )
    db.commit()


def _consume_challenge(db: Session, *, user_id: int, purpose: str) -> bytes:
    now = datetime.utcnow()
    query = db.query(AuthWebAuthnChallenge).filter(
        AuthWebAuthnChallenge.user_id == user_id,
        AuthWebAuthnChallenge.purpose == purpose,
        AuthWebAuthnChallenge.used_at.is_(None),
        AuthWebAuthnChallenge.expires_at > now,
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    row = query.order_by(AuthWebAuthnChallenge.id.desc()).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Desafio WebAuthn inválido ou expirado",
        )
    row.used_at = now
    db.commit()
    return base64url_to_bytes(row.challenge)


def _parse_credential(credential: object) -> dict:
    if isinstance(credential, str):
        try:
            credential = json.loads(credential)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credencial WebAuthn inválida",
            ) from exc
    if not isinstance(credential, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credencial WebAuthn inválida",
        )
    return credential


def _transports_from_row(row: WebAuthnCredential) -> list[AuthenticatorTransport] | None:
    if not row.transports:
        return None
    out: list[AuthenticatorTransport] = []
    for part in row.transports.split(","):
        value = part.strip()
        if not value:
            continue
        try:
            out.append(AuthenticatorTransport(value))
        except ValueError:
            continue
    return out or None


def _credential_descriptors(rows: list[WebAuthnCredential]) -> list[PublicKeyCredentialDescriptor]:
    descriptors: list[PublicKeyCredentialDescriptor] = []
    for row in rows:
        try:
            cred_id = base64url_to_bytes(row.credential_id)
        except Exception:
            continue
        descriptors.append(
            PublicKeyCredentialDescriptor(
                id=cred_id,
                transports=_transports_from_row(row),
            )
        )
    return descriptors


def _find_user_by_username(db: Session, username: str) -> User | None:
    value = (username or "").strip()
    if not value:
        return None
    if "@" in value:
        return db.query(User).filter(User.email == value.lower()).first()
    phone = normalize_phone(value)
    if not phone:
        return None
    return db.query(User).filter(User.phone == phone).first()


def registration_options(db: Session, user: User) -> dict:
    existing = (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user.id)
        .all()
    )
    user_name = (user.email or user.phone or str(user.id)).strip()
    options = generate_registration_options(
        rp_id=rp_id(),
        rp_name=rp_name(),
        user_name=user_name,
        user_id=str(user.id).encode("utf-8"),
        user_display_name=(user.name or user_name)[:120],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=_credential_descriptors(existing) or None,
    )
    payload = json.loads(options_to_json(options))
    _store_challenge(
        db,
        challenge_b64=payload["challenge"],
        user_id=user.id,
        purpose=PURPOSE_REGISTER,
    )
    return payload


def verify_registration(
    db: Session,
    user: User,
    credential: object,
    device_name: str | None = None,
) -> WebAuthnCredential:
    expected = _consume_challenge(db, user_id=user.id, purpose=PURPOSE_REGISTER)
    cred = _parse_credential(credential)
    try:
        verification = verify_registration_response(
            credential=cred,
            expected_challenge=expected,
            expected_rp_id=rp_id(),
            expected_origin=rp_origin(),
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falha ao verificar passkey",
        ) from exc

    cred_id = bytes_to_base64url(verification.credential_id)
    duplicate = (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.credential_id == cred_id)
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passkey já cadastrada",
        )

    transports = cred.get("response", {}).get("transports") or cred.get("transports")
    transport_str = None
    if isinstance(transports, list):
        transport_str = ",".join(str(t) for t in transports if t)[:255] or None

    name = (device_name or "").strip()[:120] or "Passkey"
    row = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id,
        public_key=verification.credential_public_key,
        sign_count=int(verification.sign_count or 0),
        transports=transport_str,
        device_name=name,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def login_options(db: Session, username: str) -> dict:
    user = _find_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passkey indisponível",
        )
    rows = (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user.id)
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passkey indisponível",
        )
    options = generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=_credential_descriptors(rows),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    payload = json.loads(options_to_json(options))
    _store_challenge(
        db,
        challenge_b64=payload["challenge"],
        user_id=user.id,
        purpose=PURPOSE_LOGIN,
    )
    return payload


def verify_login(db: Session, username: str, credential: object) -> User:
    user = _find_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )
    cred = _parse_credential(credential)
    cred_id = cred.get("id")
    if not isinstance(cred_id, str) or not cred_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credencial WebAuthn inválida",
        )
    row = (
        db.query(WebAuthnCredential)
        .filter(
            WebAuthnCredential.user_id == user.id,
            WebAuthnCredential.credential_id == cred_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )
    expected = _consume_challenge(db, user_id=user.id, purpose=PURPOSE_LOGIN)
    try:
        verification = verify_authentication_response(
            credential=cred,
            expected_challenge=expected,
            expected_rp_id=rp_id(),
            expected_origin=rp_origin(),
            credential_public_key=row.public_key,
            credential_current_sign_count=int(row.sign_count or 0),
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        ) from exc

    row.sign_count = int(verification.new_sign_count or row.sign_count or 0)
    row.last_used_at = datetime.utcnow()
    db.commit()
    return user


def list_passkeys(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user_id)
        .order_by(WebAuthnCredential.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "device_name": row.device_name,
            "created_at": row.created_at,
            "last_used_at": row.last_used_at,
        }
        for row in rows
    ]


def delete_passkey(db: Session, user_id: int, credential_id: int) -> None:
    row = db.get(WebAuthnCredential, credential_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Passkey não encontrada")
    db.delete(row)
    db.commit()
