#!/usr/bin/env python3
"""Gera chaves VAPID no .env se ainda não existirem. Não imprime o valor privado."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def generate_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return pem.replace("\n", "\\n"), _b64url(public)


def has_keys(text: str) -> bool:
    pub = any(line.startswith("VAPID_PUBLIC_KEY=") and len(line.strip()) > 18 for line in text.splitlines())
    priv = any(line.startswith("VAPID_PRIVATE_KEY=") and len(line.strip()) > 19 for line in text.splitlines())
    return pub and priv


def main() -> int:
    env_path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    if not env_path.is_file():
        print("vapid_ready=0 missing_env", flush=True)
        return 1
    current = env_path.read_text(encoding="utf-8")
    if has_keys(current):
        print("vapid_ready=1 already", flush=True)
        return 0
    pem, public = generate_pair()
    block = (
        "\n# Web Push (Financeiro). Gerado automaticamente; não versionar o valor privado.\n"
        f"VAPID_PUBLIC_KEY={public}\n"
        f"VAPID_PRIVATE_KEY={pem}\n"
        "VAPID_SUBJECT=mailto:cyberhost@ruts.dev\n"
    )
    with env_path.open("a", encoding="utf-8") as handle:
        handle.write(block)
    print("vapid_ready=1 created", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
