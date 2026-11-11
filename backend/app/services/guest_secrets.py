"""Envelope das senhas administrativas Windows persistidas em vps_instances."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

SEAL_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"winpwd:{get_settings().secret_key}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_sealed(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(SEAL_PREFIX)


def seal_windows_password(plain: str | None) -> str | None:
    if plain is None or plain == "":
        return None
    if is_sealed(plain):
        return plain
    token = _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    return f"{SEAL_PREFIX}{token}"


def open_windows_password(stored: str | None) -> str | None:
    """Devolve a senha em claro. Texto legado (pré-SEC-024) passa direto."""
    if stored is None or stored == "":
        return None
    if not is_sealed(stored):
        return stored
    try:
        return _fernet().decrypt(stored[len(SEAL_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        logger.error("Falha ao abrir senha Windows persistida (token inválido)")
        return None


def instance_windows_password(instance) -> str | None:
    return open_windows_password(getattr(instance, "windows_admin_password", None))


def set_instance_windows_password(instance, plain: str | None) -> None:
    instance.windows_admin_password = seal_windows_password(plain)


def seal_legacy_windows_passwords(db) -> int:
    """Cifra linhas que ainda estão em texto puro. Não registra o valor."""
    from app.models.vps import VpsInstance

    rows = (
        db.query(VpsInstance)
        .filter(VpsInstance.windows_admin_password.isnot(None))
        .all()
    )
    changed = 0
    for row in rows:
        stored = row.windows_admin_password
        if not stored or is_sealed(stored):
            continue
        row.windows_admin_password = seal_windows_password(stored)
        changed += 1
    if changed:
        db.commit()
        logger.info("Cifradas %s senha(s) Windows que estavam em texto puro", changed)
    return changed
