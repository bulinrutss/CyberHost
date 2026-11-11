"""Normalização e validação de telefone (Brasil)."""

from __future__ import annotations

import re


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone.strip())
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits


def validate_phone(phone: str) -> str:
    normalized = normalize_phone(phone)
    if len(normalized) < 10 or len(normalized) > 11:
        raise ValueError("Telefone inválido — use DDD + número (10 ou 11 dígitos)")
    return normalized


def to_whatsapp_e164(phone: str) -> str:
    """DDI 55 + DDD + número, sem '+' — formato da Cloud API."""
    return f"55{validate_phone(phone)}"
