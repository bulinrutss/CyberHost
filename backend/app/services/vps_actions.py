"""Ações sobre instâncias VPS (cliente e administrador)."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from pyVmomi import vim
from sqlalchemy.orm import Session, joinedload

from app.config import Settings, get_settings
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder, VpsPlan, VpsPlanPreset, VpsStatus
from app.services.guest_secrets import (
    instance_windows_password,
    set_instance_windows_password,
)
from app.services.vmware.client import esxi_session
from app.services.vmware.configure import destroy_vm, power_off, power_on, reset_vm, wait_for_tools
from app.services.vmware.guest_ops import set_windows_password, set_windows_static_ip
from app.services.vmware.ip_pool import validate_ip_available
from app.services.billing import assert_billing_allows_operations, calculate_monthly_cents, get_billing_snapshot
from app.services.os_templates import guest_username_for_os, os_label_for_slug
from app.services.provision_progress import provision_fields_for_instance, sanitize_customer_error
from app.services.vmware.metrics import collect_vm_metrics, metrics_from_db

logger = logging.getLogger(__name__)


def resolve_instance(
    db: Session,
    instance_id: int,
    user: User | None = None,
    *,
    admin: bool = False,
) -> VpsInstance:
    instance = (
        db.query(VpsInstance)
        .options(
            joinedload(VpsInstance.order).joinedload(VpsOrder.plan),
            joinedload(VpsInstance.plan),
        )
        .filter(VpsInstance.id == instance_id)
        .first()
    )
    if not instance or instance.status == VpsStatus.DELETED:
        raise HTTPException(status_code=404, detail="VPS não encontrada")
    if not admin and (user is None or instance.user_id != user.id):
        raise HTTPException(status_code=404, detail="VPS não encontrada")
    return instance


def _guest_password(instance: VpsInstance, settings: Settings) -> str | None:
    return instance_windows_password(instance) or settings.guest_admin_password or None


def _get_vm(client, instance: VpsInstance) -> vim.VirtualMachine:
    vm = client.find_vm_by_name(instance.vm_name)
    if not vm:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    return vm


def normalize_power_state(vm: vim.VirtualMachine) -> str:
    state = vm.runtime.powerState
    if state == vim.VirtualMachinePowerState.poweredOn:
        return "poweredOn"
    if state == vim.VirtualMachinePowerState.poweredOff:
        return "poweredOff"
    if state == vim.VirtualMachinePowerState.suspended:
        return "suspended"
    return "unknown"


def _is_powered_on(vm: vim.VirtualMachine) -> bool:
    return vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn


def _tools_ok(vm: vim.VirtualMachine) -> bool:
    guest = vm.guest
    return bool(
        guest
        and guest.toolsStatus == vim.vm.GuestInfo.ToolsStatus.toolsOk
        and guest.toolsRunningStatus == vim.vm.GuestInfo.ToolsRunningStatus.guestToolsRunning
    )


def _runtime_from_vm(vm: vim.VirtualMachine, *, ram_allocated_mb: int | None = None) -> dict:
    metrics = collect_vm_metrics(vm, ram_allocated_mb=ram_allocated_mb)
    return {
        "power_state": normalize_power_state(vm),
        "tools_ok": _tools_ok(vm),
        "metrics": metrics,
    }


def _offline_runtime(instance: VpsInstance, *, power_state: str = "unknown") -> dict:
    return {
        "power_state": power_state,
        "tools_ok": False,
        "metrics": metrics_from_db(
            instance.vcpu,
            instance.ram_mb,
            disk_gb=instance.disk_gb or None,
        ),
    }


def _fetch_vm_map(client) -> dict[str, vim.VirtualMachine]:
    container = client.content.viewManager.CreateContainerView(
        client.content.rootFolder, [vim.VirtualMachine], True
    )
    try:
        return {vm.name: vm for vm in container.view}
    finally:
        container.Destroy()


def get_instance_live_status(instance: VpsInstance) -> dict:
    """Consulta estado real da VM no ESXi (sem lançar exceção se offline)."""
    try:
        with esxi_session() as client:
            vm = client.find_vm_by_name(instance.vm_name)
            if not vm:
                return _offline_runtime(instance, power_state="not_found")
            return _runtime_from_vm(vm, ram_allocated_mb=instance.ram_mb)
    except Exception:
        return _offline_runtime(instance)


def _ensure_powered_on_with_tools(client, vm: vim.VirtualMachine) -> None:
    if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
        power_on(client, vm)
    wait_for_tools(client, vm, timeout=300)


def power_on_instance(instance: VpsInstance) -> str:
    assert_billing_allows_operations(instance, action="ligar")
    with esxi_session() as client:
        vm = _get_vm(client, instance)
        if _is_powered_on(vm):
            raise HTTPException(status_code=400, detail="A VM já está ligada")
        power_on(client, vm)
    instance.status = VpsStatus.RUNNING
    return "VM ligada"


def power_off_instance(instance: VpsInstance) -> str:
    with esxi_session() as client:
        vm = _get_vm(client, instance)
        if not _is_powered_on(vm):
            raise HTTPException(status_code=400, detail="A VM já está desligada")
        power_off(client, vm)
    instance.status = VpsStatus.STOPPED
    return "VM desligada"


def reset_instance(instance: VpsInstance) -> str:
    assert_billing_allows_operations(instance, action="reiniciar")
    with esxi_session() as client:
        vm = _get_vm(client, instance)
        if not _is_powered_on(vm):
            raise HTTPException(
                status_code=400,
                detail="A VM está desligada — use Ligar antes de reiniciar",
            )
        reset_vm(client, vm)
    instance.status = VpsStatus.RUNNING
    return "VM reiniciada"


def change_instance_ip(
    db: Session,
    instance: VpsInstance,
    new_ip: str,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    try:
        validate_ip_available(db, settings, new_ip, exclude_instance_id=instance.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    guest_pwd = _guest_password(instance, settings)
    with esxi_session(settings) as client:
        vm = _get_vm(client, instance)
        _ensure_powered_on_with_tools(client, vm)
        set_windows_static_ip(client, vm, settings, new_ip, password=guest_pwd)

    instance.ip_address = new_ip
    return f"IP alterado para {new_ip}"


def change_instance_password(
    instance: VpsInstance,
    username: str,
    new_password: str,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    current_pwd = _guest_password(instance, settings)
    if not current_pwd:
        raise HTTPException(
            status_code=400,
            detail="Senha do guest não configurada (GUEST_ADMIN_PASSWORD)",
        )

    with esxi_session(settings) as client:
        vm = _get_vm(client, instance)
        _ensure_powered_on_with_tools(client, vm)
        set_windows_password(
            client,
            vm,
            settings,
            username,
            new_password,
            current_password=current_pwd,
        )

    if username.lower() == settings.guest_admin_user.lower():
        set_instance_windows_password(instance, new_password)
    return "Senha alterada com sucesso"


def _resolve_plan(instance: VpsInstance) -> VpsPlan | None:
    plan: VpsPlan | None = instance.plan
    if plan is None and instance.order and instance.order.plan:
        plan = instance.order.plan
    return plan


def _plan_fields(
    instance: VpsInstance,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> dict:
    plan = _resolve_plan(instance)
    monthly_cents = (
        calculate_monthly_cents(plan, instance, plan_presets=plan_presets) if plan else None
    )
    billing = get_billing_snapshot(instance, monthly_cents=monthly_cents) if instance.paid_until else None
    return {
        "disk_gb": instance.disk_gb or (plan.default_disk_gb if plan else 30),
        "network_mbps": instance.network_mbps or (plan.network_mbps if plan else 300),
        "plan_slug": plan.slug if plan else None,
        "plan_name": plan.name if plan else None,
        "billing": billing,
    }


def _is_non_critical_guest_error(message: str | None) -> bool:
    """Timeouts de processo guest (ex.: rearm) não bloqueiam uso da VPS."""
    text = (message or "").strip().lower()
    if not text:
        return False
    return "processo guest" in text and "não terminou" in text


def public_error_message(instance: VpsInstance) -> str | None:
    """Erro exibido ao cliente — omite falhas guest não críticas se a VPS já tem IP/senha."""
    msg = instance.error_message
    if not msg:
        return None
    if _is_non_critical_guest_error(msg) and (
        instance.windows_admin_password or instance.ip_address
    ):
        return None
    return sanitize_customer_error(msg)


def heal_non_critical_guest_error(db, instance: VpsInstance) -> bool:
    """Se o único problema foi timeout guest não crítico, marca VPS como running."""
    if instance.status != VpsStatus.ERROR:
        return False
    if not _is_non_critical_guest_error(instance.error_message):
        return False
    if not instance.windows_admin_password and not instance.ip_address:
        return False
    instance.status = VpsStatus.RUNNING
    instance.error_message = None
    try:
        db.add(instance)
        db.commit()
        db.refresh(instance)
    except Exception:
        db.rollback()
        return False
    return True


def _windows_credentials(
    instance: VpsInstance,
    *,
    include_secrets: bool = False,
) -> dict | None:
    password = instance_windows_password(instance)
    if not password:
        return None
    # ERROR com senha ainda pode ter RDP (ex.: timeout no rearm após configurar tudo).
    if instance.status in (VpsStatus.DELETED, VpsStatus.CREATING):
        return None
    os_template = getattr(instance, "os_template", None) or (
        instance.order.os_template if instance.order else None
    )
    username = guest_username_for_os(os_template)
    if not include_secrets:
        return {
            "username": username,
            "password": None,
            "has_password": True,
        }
    logger.info(
        "Windows credentials reveladas instance_id=%s user_id=%s",
        instance.id,
        instance.user_id,
    )
    return {
        "username": username,
        "password": password,
        "has_password": True,
    }


def get_windows_credentials(
    instance: VpsInstance,
    *,
    include_secrets: bool = False,
) -> dict | None:
    return _windows_credentials(instance, include_secrets=include_secrets)


def _instance_base(
    instance: VpsInstance,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> dict:
    os_template = getattr(instance, "os_template", None) or (
        instance.order.os_template if instance.order else None
    )
    return {
        "id": instance.id,
        "vm_name": instance.vm_name,
        "vcpu": instance.vcpu,
        "ram_mb": instance.ram_mb,
        **_plan_fields(instance, plan_presets=plan_presets),
        "os_template": os_template,
        "os_label": os_label_for_slug(os_template),
        "ip_address": instance.ip_address,
        "status": instance.status,
        "esxi_host": instance.esxi_host,
        "error_message": public_error_message(instance),
        "created_at": instance.created_at,
        **provision_fields_for_instance(instance),
    }


def build_instance_list_item(
    instance: VpsInstance,
    vm: vim.VirtualMachine | None,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> dict:
    base = _instance_base(instance, plan_presets=plan_presets)
    if vm:
        runtime = _runtime_from_vm(vm, ram_allocated_mb=instance.ram_mb)
        metrics = runtime["metrics"]
        base.update(
            {
                "power_state": runtime["power_state"],
                "cpu_usage_percent": metrics["cpu_usage_percent"],
                "ram_usage_percent": metrics["ram_usage_percent"],
                "disk_allocated_gb": metrics["disk_allocated_gb"],
                "disk_usage_percent": metrics["disk_usage_percent"],
            }
        )
    else:
        base.update(
            {
                "power_state": "not_found",
                "cpu_usage_percent": None,
                "ram_usage_percent": None,
                "disk_allocated_gb": None,
                "disk_usage_percent": None,
            }
        )
    return base


def build_instances_list(instances: list[VpsInstance]) -> list[dict]:
    if not instances:
        return []
    try:
        with esxi_session() as client:
            vm_map = _fetch_vm_map(client)
            return [build_instance_list_item(inst, vm_map.get(inst.vm_name)) for inst in instances]
    except Exception:
        return [
            build_instance_list_item(inst, None) for inst in instances
        ]


def build_instance_detail(
    instance: VpsInstance,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
    db: Session | None = None,
    include_secrets: bool = False,
) -> dict:
    from app.services.port_proxy import (
        get_port_mappings_for_ip,
        get_rdp_mapping,
        port_mapping_to_dict,
    )
    from app.services.vps_connection_domains import connection_to_dict, list_for_instance
    from app.services.web_slug import dns_target_host

    live = get_instance_live_status(instance)
    port_mappings = get_port_mappings_for_ip(instance.ip_address)
    rdp_mapping = get_rdp_mapping(instance.ip_address)
    connection_domains = (
        [connection_to_dict(c) for c in list_for_instance(db, instance)] if db is not None else []
    )
    return {
        **_instance_base(instance, plan_presets=plan_presets),
        "power_state": live["power_state"],
        "tools_ok": live["tools_ok"],
        "metrics": live["metrics"],
        "windows_credentials": _windows_credentials(
            instance, include_secrets=include_secrets
        ),
        "port_mappings": [port_mapping_to_dict(m) for m in port_mappings],
        "connection_domains": connection_domains,
        "dns_target": dns_target_host() if db is not None else "",
        "rdp_connection_address": rdp_mapping.connection_address if rdp_mapping else None,
    }


def destroy_instance(instance: VpsInstance) -> str:
    with esxi_session() as client:
        vm = client.find_vm_by_name(instance.vm_name)
        if vm:
            destroy_vm(client, vm)
    instance.status = VpsStatus.DELETED
    instance.ip_address = None
    instance.windows_admin_password = None
    return "VPS removida"
