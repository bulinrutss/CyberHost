"""TOTP (RFC 6238) compatível com Google Authenticator — só biblioteca padrão."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time

DIGITS = 6
PERIOD = 30
ISSUER = "CyberHost"


def generate_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _normalize_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    pad = (8 - len(padded) % 8) % 8
    return base64.b32decode(padded + ("=" * pad), casefold=True)


def totp_code(secret: str, at: int | None = None) -> str:
    key = _normalize_secret(secret)
    counter = int((time.time() if at is None else at) // PERIOD)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % (10 ** DIGITS):0{DIGITS}d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(cleaned) != DIGITS:
        return False
    now = int(time.time())
    for delta in range(-window, window + 1):
        expected = totp_code(secret, at=now + delta * PERIOD)
        if hmac.compare_digest(expected, cleaned):
            return True
    return False


def otpauth_url(secret: str, account: str) -> str:
    label = f"{ISSUER}:{account}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"
    )
