"""Disco contratado (plano) vs disco provisionado no hypervisor."""

from __future__ import annotations

# Espaço extra no VMDK para o Windows (não entra no preço nem no plano).
SYSTEM_DISK_OVERHEAD_GB = 10


def provisioned_disk_gb(contracted_gb: int) -> int:
    """Tamanho real do disco virtual: contratado + overhead do sistema."""
    return int(contracted_gb) + SYSTEM_DISK_OVERHEAD_GB
