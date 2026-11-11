"""Validação de hostname / nome de VM."""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.vps import OrderStatus, VpsInstance, VpsOrder, VpsStatus

ACTIVE_ORDER_STATUSES = (
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.PAID,
    OrderStatus.PROVISIONING,
    OrderStatus.ACTIVE,
)

HOSTNAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$")
HOSTNAME_INVALID_MESSAGE = (
    "O hostname só pode ter letras sem acento, números e hífen. "
    "Não use espaços, ç, ã, é nem outros caracteres especiais. "
    "Exemplo: meu-servidor"
)


def validate_hostname(hostname: str) -> str:
    """Normaliza e valida o hostname visível ao cliente."""
    normalized = hostname.strip().lower()
    if len(normalized) < 3 or len(normalized) > 63:
        raise ValueError("O hostname deve ter entre 3 e 63 caracteres.")
    if not HOSTNAME_PATTERN.fullmatch(normalized):
        raise ValueError(HOSTNAME_INVALID_MESSAGE)
    return normalized


def vm_name_from_hostname(hostname: str) -> str:
    return f"VPS-{hostname.upper()}"


def assert_hostname_available(
    db: Session,
    hostname: str,
    *,
    exclude_order_id: int | None = None,
) -> str:
    """Garante que o hostname ainda não está em uso. Retorna o vm_name."""
    normalized = hostname.lower().strip()
    vm_name = vm_name_from_hostname(normalized)

    instance = (
        db.query(VpsInstance)
        .filter(VpsInstance.vm_name == vm_name, VpsInstance.status != VpsStatus.DELETED)
        .first()
    )
    if instance:
        raise HTTPException(
            status_code=400,
            detail=f"O hostname '{normalized}' já está em uso. Escolha outro nome.",
        )

    pending_query = db.query(VpsOrder).filter(
        VpsOrder.hostname == normalized,
        VpsOrder.status.in_(ACTIVE_ORDER_STATUSES),
    )
    if exclude_order_id is not None:
        pending_query = pending_query.filter(VpsOrder.id != exclude_order_id)
    pending_order = pending_query.first()
    if pending_order:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um pedido ativo com o hostname '{normalized}'.",
        )

    return vm_name
