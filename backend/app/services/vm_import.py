"""Importação de VMs existentes no ESXi para o painel."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsPlan, VpsStatus
from app.services.billing import initial_paid_until
from app.services.guest_secrets import set_instance_windows_password
from app.services.hostname import vm_name_from_hostname
from app.services.os_templates import all_template_names

if TYPE_CHECKING:
    from app.services.vmware.client import ESXiClient

VM_PREFIX = re.compile(r"^VPS-", re.IGNORECASE)
VM_PREFIX_LOOSE = re.compile(r"^VPS[\s\-_]", re.IGNORECASE)


def _hostname_from_vm_name(vm_name: str) -> str:
    if VM_PREFIX.match(vm_name):
        return vm_name[4:].lower()
    if vm_name.upper().startswith("VPS"):
        rest = vm_name[3:].lstrip(" -_")
        slug = re.sub(r"[^a-z0-9]+", "-", rest.lower()).strip("-")
        return slug or vm_name.lower()
    return vm_name.lower()


def _suggested_client_name(vm_name: str) -> str:
    host = _hostname_from_vm_name(vm_name)
    return host.replace("-", " ").title()


def _disk_gb_from_vm(vm: Any) -> int:
    from app.services.vmware.metrics import _virtual_disk_capacity_bytes

    total_bytes = _virtual_disk_capacity_bytes(vm)
    if total_bytes <= 0:
        return 70
    return max(1, round(total_bytes / (1024**3)))


def _guess_plan_slug(vcpu: int, ram_mb: int) -> str:
    if vcpu > 8 or ram_mb > 8192:
        return "semi_dedicated"
    return "vps"


def _status_from_power(power_state: str) -> VpsStatus:
    if "poweredOn" in power_state:
        return VpsStatus.RUNNING
    if "poweredOff" in power_state:
        return VpsStatus.STOPPED
    return VpsStatus.RUNNING


def resolve_import_user(db: Session, user_id: int | None) -> User:
    if not user_id:
        raise HTTPException(status_code=400, detail="Selecione uma conta existente")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Conta não encontrada. Cadastre o cliente antes de importar.",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Conta inativa")
    return user


def _is_importable_vm_name(name: str, template_name: str | None = None) -> bool:
    if name in all_template_names():
        return False
    if template_name and name == template_name:
        return False
    upper = name.upper()
    if upper in ("VPSHOST", "PROXY"):
        return False
    if VM_PREFIX.match(name) or VM_PREFIX_LOOSE.match(name):
        return True
    return upper.startswith("VPS") and len(name) > 3


def _registered_vm_names(db: Session) -> set[str]:
    rows = (
        db.query(VpsInstance.vm_name)
        .filter(VpsInstance.status != VpsStatus.DELETED)
        .all()
    )
    return {row[0] for row in rows}


def _vm_to_discover_item(vm: Any) -> dict:
    summary = vm.summary
    power_state = str(summary.runtime.powerState)
    vcpu = int(summary.config.numCpu)
    ram_mb = int(summary.config.memorySizeMB)
    return {
        "vm_name": vm.name,
        "vm_moid": vm._moId,
        "hostname": _hostname_from_vm_name(vm.name),
        "suggested_name": _suggested_client_name(vm.name),
        "vcpu": vcpu,
        "ram_mb": ram_mb,
        "disk_gb": _disk_gb_from_vm(vm),
        "ip_address": summary.guest.ipAddress if summary.guest else None,
        "power_state": power_state,
        "guest_os": summary.config.guestFullName,
        "suggested_plan_slug": _guess_plan_slug(vcpu, ram_mb),
    }


def discover_unregistered_vms(db: Session, settings: Settings | None = None) -> dict:
    from pyVmomi import vim
    from app.services.vmware.client import esxi_session

    settings = settings or get_settings()
    registered = _registered_vm_names(db)

    with esxi_session(settings) as client:
        container = client.content.viewManager.CreateContainerView(
            client.content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            unregistered: list[dict] = []
            already_registered: list[str] = []
            skipped: list[dict] = []

            for vm in container.view:
                name = vm.name
                if not _is_importable_vm_name(name, settings.esxi_template_name):
                    if name != settings.esxi_template_name:
                        skipped.append({"vm_name": name, "reason": "nome fora do padrão VPS-"})
                    continue

                if name in registered:
                    already_registered.append(name)
                    continue

                unregistered.append(_vm_to_discover_item(vm))
        finally:
            container.Destroy()

    unregistered.sort(key=lambda item: item["vm_name"])
    return {
        "template_name": settings.esxi_template_name,
        "unregistered": unregistered,
        "already_registered": sorted(already_registered),
        "skipped": skipped,
    }


def import_vms(
    db: Session,
    items: list[dict],
    *,
    settings: Settings | None = None,
) -> dict:
    from app.services.vmware.client import esxi_session

    settings = settings or get_settings()
    registered = _registered_vm_names(db)

    if not items:
        raise HTTPException(status_code=400, detail="Nenhuma VM selecionada para importar")

    plans = {p.slug: p for p in db.query(VpsPlan).filter(VpsPlan.is_active.is_(True)).all()}
    if "vps" not in plans:
        raise HTTPException(status_code=500, detail="Plano VPS não configurado")

    imported: list[dict] = []
    errors: list[dict] = []

    with esxi_session(settings) as client:
        for item in items:
            vm_name = (item.get("vm_name") or "").strip()
            try:
                result = _import_single_vm(
                    db,
                    client,
                    item,
                    registered=registered,
                    plans=plans,
                    settings=settings,
                )
                registered.add(vm_name)
                imported.append(result)
            except HTTPException as exc:
                errors.append({"vm_name": vm_name, "error": exc.detail})
            except Exception as exc:
                errors.append({"vm_name": vm_name, "error": str(exc)})

    db.commit()
    return {"imported": imported, "errors": errors}


def _import_single_vm(
    db: Session,
    client: ESXiClient,
    item: dict,
    *,
    registered: set[str],
    plans: dict[str, VpsPlan],
    settings: Settings,
) -> dict:
    vm_name = (item["vm_name"] or "").strip()
    if not vm_name:
        raise HTTPException(status_code=400, detail="vm_name obrigatório")

    if vm_name in registered:
        raise HTTPException(status_code=400, detail="VM já registrada no painel")

    if not _is_importable_vm_name(vm_name, settings.esxi_template_name):
        raise HTTPException(status_code=400, detail="VM fora do padrão VPS- ou é o template")

    user = resolve_import_user(db, item.get("user_id"))

    plan_slug = item.get("plan_slug") or None
    vm = client.find_vm_by_name(vm_name)
    if not vm:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    summary = vm.summary
    vcpu = int(item.get("vcpu") or summary.config.numCpu)
    ram_mb = int(item.get("ram_mb") or summary.config.memorySizeMB)
    disk_gb = int(item.get("disk_gb") or _disk_gb_from_vm(vm))
    ip_address = item.get("ip_address") or (summary.guest.ipAddress if summary.guest else None)

    if not plan_slug:
        plan_slug = _guess_plan_slug(vcpu, ram_mb)
    plan = plans.get(plan_slug) or plans["vps"]

    hostname = _hostname_from_vm_name(vm_name)
    expected_vm_name = vm_name_from_hostname(hostname)
    if expected_vm_name != vm_name:
        hostname = vm_name.lower()

    order = VpsOrder(
        user_id=user.id,
        plan_id=plan.id,
        vcpu=vcpu,
        ram_mb=ram_mb,
        disk_gb=disk_gb,
        hostname=hostname,
        order_type=OrderType.NEW,
        status=OrderStatus.ACTIVE,
        total_cents=0,
        payment_provider="import",
        provision_progress=100,
        provision_step="ready",
    )
    db.add(order)
    db.flush()

    paid_until, billing_day = initial_paid_until()
    instance = VpsInstance(
        user_id=user.id,
        order_id=order.id,
        plan_id=plan.id,
        vm_name=vm_name,
        vm_moid=vm._moId,
        vcpu=vcpu,
        ram_mb=ram_mb,
        disk_gb=disk_gb,
        network_mbps=plan.network_mbps,
        ip_address=ip_address,
        status=_status_from_power(str(summary.runtime.powerState)),
        esxi_host=settings.esxi_host,
        paid_until=paid_until,
        billing_day=billing_day,
        suspended_for_billing=False,
    )
    set_instance_windows_password(instance, settings.guest_admin_password or None)
    db.add(instance)
    db.flush()

    return {
        "vm_name": vm_name,
        "user_id": user.id,
        "instance_id": instance.id,
        "phone": user.phone,
        "name": user.name,
        "email": user.email,
        "plan_slug": plan.slug,
    }
