"""Aplicação de upgrades pagos em VPS existentes."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from pyVmomi import vim

from app.config import get_settings
from app.models.vps import OrderStatus, VpsInstance, VpsOrder, VpsPlan, VpsStatus
from app.services.billing import apply_upgrade_to_custom_monthly, calculate_monthly_cents
from app.services.guest_secrets import instance_windows_password
from app.services.plan_presets import list_plan_presets
from app.services.pricing import calculate_upgrade_monthly_delta
from app.services.disk_policy import provisioned_disk_gb
from app.services.provision_progress import update_order_progress
from app.services.vmware.client import esxi_session
from app.services.vmware.configure import apply_resource_upgrade, power_off, power_on, wait_for_tools
from app.services.vmware.guest_ops import extend_windows_c_volume

logger = logging.getLogger(__name__)


def apply_upgrade_order(db: Session, order: VpsOrder) -> VpsInstance:
    if not order.target_instance_id:
        raise ValueError("Pedido de upgrade sem instância alvo")

    instance = db.get(VpsInstance, order.target_instance_id)
    if not instance or instance.status == VpsStatus.DELETED:
        raise ValueError("Instância alvo não encontrada")

    monthly_delta = 0
    if order.upgrade_monthly_delta_cents is not None:
        monthly_delta = int(order.upgrade_monthly_delta_cents)
    else:
        plan = db.get(VpsPlan, instance.plan_id) if instance.plan_id else None
        if plan:
            presets = list_plan_presets(db, plan.id)
            try:
                monthly_delta = calculate_upgrade_monthly_delta(
                    plan,
                    instance,
                    order.vcpu,
                    order.ram_mb,
                    order.disk_gb,
                    plan_presets=presets,
                )
            except Exception:
                logger.exception(
                    "Não foi possível calcular delta mensal do upgrade (pedido %s)", order.id
                )

    current_plan = db.get(VpsPlan, instance.plan_id) if instance.plan_id else None
    current_presets = list_plan_presets(db, current_plan.id) if current_plan else []
    current_monthly = (
        calculate_monthly_cents(current_plan, instance, plan_presets=current_presets)
        if current_plan
        else int(instance.custom_monthly_cents or 0)
    )

    update_order_progress(db, order, progress=20, step="configuring")

    needs_hw = order.vcpu != instance.vcpu or order.ram_mb != instance.ram_mb
    needs_disk = order.disk_gb > instance.disk_gb

    if needs_hw or needs_disk:
        settings = get_settings()
        guest_pwd = instance_windows_password(instance) or settings.guest_admin_password

        with esxi_session() as client:
            vm = client.find_vm_by_name(instance.vm_name)
            if not vm:
                raise ValueError("Servidor não encontrado")

            initially_on = vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn

            update_order_progress(db, order, progress=40, step="powering_off")
            was_powered_on = apply_resource_upgrade(
                client,
                vm,
                vcpu=order.vcpu if needs_hw else None,
                ram_mb=order.ram_mb if needs_hw else None,
                disk_gb=provisioned_disk_gb(order.disk_gb) if needs_disk else None,
            )

            if needs_disk:
                update_order_progress(db, order, progress=70, step="extending_disk")
                if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
                    power_on(client, vm)
                wait_for_tools(client, vm, timeout=300)
                extend_windows_c_volume(client, vm, settings, password=guest_pwd)
                if not initially_on and not was_powered_on:
                    power_off(client, vm)

            update_order_progress(db, order, progress=85, step="configuring")
            if needs_hw:
                instance.status = VpsStatus.RUNNING if was_powered_on else VpsStatus.STOPPED
            elif needs_disk:
                instance.status = (
                    VpsStatus.RUNNING
                    if (initially_on or was_powered_on)
                    else VpsStatus.STOPPED
                )

    instance.vcpu = order.vcpu
    instance.ram_mb = order.ram_mb
    instance.disk_gb = order.disk_gb
    target_plan = db.get(VpsPlan, order.plan_id)
    if target_plan:
        instance.plan_id = target_plan.id
        instance.network_mbps = target_plan.network_mbps
    if instance.paid_until:
        instance.billing_day = instance.paid_until.day
    if monthly_delta > 0:
        instance.custom_monthly_cents = current_monthly + monthly_delta
    else:
        apply_upgrade_to_custom_monthly(instance, monthly_delta)
    instance.error_message = None
    order.status = OrderStatus.ACTIVE
    order.error_message = None
    update_order_progress(db, order, progress=100, step="ready")
    db.commit()
    db.refresh(instance)
    from app.services import host_notify

    host_notify.on_provision_ready(
        db,
        kind="Upgrade VPS",
        summary=instance.vm_name or f"pedido #{order.id}",
        customer_user_id=order.user_id,
        client_url="/dashboard",
    )
    logger.info(
        "Upgrade aplicado na VPS %s (pedido %s): %s vCPU, %s MB RAM, %s GB disco",
        instance.vm_name,
        order.id,
        instance.vcpu,
        instance.ram_mb,
        instance.disk_gb,
    )
    return instance
