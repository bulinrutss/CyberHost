"""Utilitários de disco virtual no ESXi."""

from __future__ import annotations

from pyVmomi import vim

from app.services.vmware.client import ESXiClient
from app.services.vmware.configure import extend_virtual_disk
from app.services.vmware.metrics import _virtual_disk_capacity_bytes

MIN_DISK_GB = 30


def vm_disk_gb(vm: vim.VirtualMachine) -> int:
    """Capacidade alocada do disco virtual da VM em GB (arredondado)."""
    total_bytes = _virtual_disk_capacity_bytes(vm)
    if total_bytes <= 0:
        return MIN_DISK_GB
    return max(1, round(total_bytes / (1024**3)))


def normalize_disk_gb(disk_gb: int, *, plan_default: int = MIN_DISK_GB) -> int:
    """Garante disco contratado >= mínimo do plano (30 GB)."""
    return max(disk_gb, plan_default, MIN_DISK_GB)


def expand_vm_disk_if_needed(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    target_disk_gb: int,
) -> bool:
    """
    Expande o disco virtual se target_disk_gb for maior que o alocado.
    Retorna True se houve expansão (requer extend do volume C: no guest depois).
    """
    target_disk_gb = max(target_disk_gb, MIN_DISK_GB)
    current_gb = vm_disk_gb(vm)
    if target_disk_gb <= current_gb:
        return False
    extend_virtual_disk(client, vm, target_disk_gb)
    return True
