"""Geração de senhas fortes para contas Windows."""

from __future__ import annotations

import secrets
import string


def generate_windows_password(length: int = 16) -> str:
    """Senha com maiúsculas, minúsculas, números e símbolos."""
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%&*"
    alphabet = lower + upper + digits + special

    parts = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    parts.extend(secrets.choice(alphabet) for _ in range(max(0, length - len(parts))))
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts)
