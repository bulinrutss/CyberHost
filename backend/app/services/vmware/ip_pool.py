"""Gerenciamento de pool de IPs para novas VPS."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.vps import VpsInstance, VpsStatus


@dataclass(frozen=True)
class AllocatedProxySlot:
    internal_ip: str
    proxy_page: int


def _iter_pool(start: str, end: str):
    start_ip = ipaddress.IPv4Address(start)
    end_ip = ipaddress.IPv4Address(end)
    current = int(start_ip)
    end = int(end_ip)
    while current <= end:
        yield str(ipaddress.IPv4Address(current))
        current += 1


def _used_ips(db: Session) -> set[str]:
    return {
        ip
        for (ip,) in db.query(VpsInstance.ip_address)
        .filter(VpsInstance.status != VpsStatus.DELETED)
        .filter(VpsInstance.ip_address.isnot(None))
        .all()
        if ip
    }


def allocate_proxy_slot(db: Session, settings: Settings) -> AllocatedProxySlot:
    """Aloca slot Máquina Vazia do Proxy Manager com IP interno e número da página."""
    from app.services.port_proxy import allocate_empty_machine_slot

    used = _used_ips(db)
    slot = allocate_empty_machine_slot(settings, used)
    return AllocatedProxySlot(internal_ip=slot.internal_ip, proxy_page=slot.page)


def allocate_ip(db: Session, settings: Settings) -> str:
    return allocate_proxy_slot(db, settings).internal_ip


def is_ip_in_pool(settings: Settings, ip: str) -> bool:
    try:
        target = ipaddress.IPv4Address(ip)
        start = ipaddress.IPv4Address(settings.ip_pool_start)
        end = ipaddress.IPv4Address(settings.ip_pool_end)
    except ipaddress.AddressValueError:
        return False
    return int(start) <= int(target) <= int(end)


def validate_ip_available(
    db: Session,
    settings: Settings,
    ip: str,
    *,
    exclude_instance_id: int | None = None,
) -> None:
    """Garante que o IP está no pool e não está em uso por outra VPS ativa."""
    if not is_ip_in_pool(settings, ip):
        raise ValueError(
            f"IP {ip} fora do pool ({settings.ip_pool_start}–{settings.ip_pool_end})"
        )

    query = (
        db.query(VpsInstance)
        .filter(VpsInstance.status != VpsStatus.DELETED)
        .filter(VpsInstance.ip_address == ip)
    )
    if exclude_instance_id is not None:
        query = query.filter(VpsInstance.id != exclude_instance_id)

    if query.first():
        raise ValueError(f"IP {ip} já está em uso por outra VPS")
