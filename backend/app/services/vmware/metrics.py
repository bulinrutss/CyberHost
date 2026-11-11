"""Métricas de uso e capacidade da VM via pyVmomi."""

from __future__ import annotations

from pyVmomi import vim


def _clamp_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, value)), 1)


def _virtual_disk_capacity_bytes(vm: vim.VirtualMachine) -> int:
    """Capacidade total dos discos virtuais configurados na VM."""
    total = 0
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualDisk):
            if getattr(device, "capacityInBytes", None):
                total += int(device.capacityInBytes)
            else:
                total += int(device.capacityInKB) * 1024
    return total


def _guest_disk_stats(guest: vim.vm.GuestInfo | None) -> dict | None:
    """
    Uso real de disco dentro do Windows/Linux via VMware Tools.
    capacity/freeSpace vêm em bytes.
    """
    if not guest or not guest.disk:
        return None

    total_cap = 0
    total_used = 0
    for disk in guest.disk:
        if disk.capacity is None or disk.freeSpace is None:
            continue
        cap = int(disk.capacity)
        free = int(disk.freeSpace)
        if cap <= 0:
            continue
        # Ignora drives removíveis / muito pequenos (CD-ROM etc.)
        if cap < 512 * 1024 * 1024:
            continue
        total_cap += cap
        total_used += max(0, cap - free)

    if total_cap <= 0:
        return None

    return {
        "allocated_bytes": total_cap,
        "used_bytes": total_used,
        "free_bytes": total_cap - total_used,
    }


def _storage_provisioned_bytes(storage: vim.vm.Summary.StorageSummary | None) -> int | None:
    """Espaço provisionado no datastore (ESXi), não é o uso dentro do SO."""
    if not storage:
        return None
    return int(storage.committed or 0) + int(storage.uncommitted or 0)


def collect_vm_metrics(
    vm: vim.VirtualMachine,
    *,
    ram_allocated_mb: int | None = None,
) -> dict:
    """Coleta alocação e uso em tempo real da VM no ESXi."""
    summary = vm.summary
    config = summary.config
    quick = summary.quickStats
    storage = summary.storage
    runtime = vm.runtime
    guest = vm.guest

    vcpu = config.numCpu
    ram_total_mb = ram_allocated_mb or config.memorySizeMB
    powered_on = runtime.powerState == vim.VirtualMachinePowerState.poweredOn

    cpu_usage_percent = None
    if powered_on and quick.overallCpuUsage is not None and runtime.maxCpuUsage:
        cpu_usage_percent = _clamp_percent(
            (quick.overallCpuUsage / runtime.maxCpuUsage) * 100
        )

    # guestMemoryUsage = memória ativa no guest, em MB (documentação VMware)
    ram_used_mb = None
    ram_usage_percent = None
    if powered_on and quick.guestMemoryUsage is not None:
        ram_used_mb = int(quick.guestMemoryUsage)
        if ram_total_mb > 0:
            ram_usage_percent = _clamp_percent((ram_used_mb / ram_total_mb) * 100)

    disk_allocated_gb = None
    disk_used_gb = None
    disk_free_gb = None
    disk_usage_percent = None
    disk_source = "none"

    guest_disk = _guest_disk_stats(guest)
    if guest_disk:
        disk_source = "guest"
        disk_allocated_gb = round(guest_disk["allocated_bytes"] / (1024**3), 2)
        disk_used_gb = round(guest_disk["used_bytes"] / (1024**3), 2)
        disk_free_gb = round(guest_disk["free_bytes"] / (1024**3), 2)
        disk_usage_percent = _clamp_percent(
            (guest_disk["used_bytes"] / guest_disk["allocated_bytes"]) * 100
        )
    else:
        virt_bytes = _virtual_disk_capacity_bytes(vm)
        if virt_bytes > 0:
            disk_allocated_gb = round(virt_bytes / (1024**3), 2)
            disk_source = "virtual_disk"
        if storage and storage.committed:
            # Sem Tools: espaço no datastore (não equivale ao uso no Windows)
            disk_used_gb = round(int(storage.committed) / (1024**3), 2)
            disk_source = "storage"

    return {
        "cpu_allocated": vcpu,
        "ram_allocated_mb": ram_total_mb,
        "disk_allocated_gb": disk_allocated_gb,
        "cpu_usage_percent": cpu_usage_percent,
        "ram_used_mb": ram_used_mb,
        "ram_usage_percent": ram_usage_percent,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "disk_usage_percent": disk_usage_percent,
        "disk_source": disk_source,
        "uptime_seconds": quick.uptimeSeconds if powered_on else None,
        "guest_os": config.guestFullName or None,
        "guest_ip": guest.ipAddress if guest else summary.guest.ipAddress,
    }


def metrics_from_db(vcpu: int, ram_mb: int, *, disk_gb: int | None = None) -> dict:
    """Fallback quando a VM não está no ESXi."""
    return {
        "cpu_allocated": vcpu,
        "ram_allocated_mb": ram_mb,
        "disk_allocated_gb": float(disk_gb) if disk_gb else None,
        "cpu_usage_percent": None,
        "ram_used_mb": None,
        "ram_usage_percent": None,
        "disk_used_gb": None,
        "disk_free_gb": None,
        "disk_usage_percent": None,
        "disk_source": "none",
        "uptime_seconds": None,
        "guest_os": None,
        "guest_ip": None,
    }
