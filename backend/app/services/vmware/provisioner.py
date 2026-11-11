"""Orquestrador de provisionamento de VPS no VMware ESXi."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.vps import OrderStatus, VpsInstance, VpsOrder, VpsStatus
from app.services.billing import initial_paid_until
from app.services.hostname import assert_hostname_available, vm_name_from_hostname
from app.services.os_templates import DEFAULT_OS_TEMPLATE, template_name_for_os
from app.services.passwords import generate_windows_password
from app.services.guest_secrets import set_instance_windows_password
from app.services.provision_progress import disk_copy_progress, update_order_progress
from app.services.vmware.client import esxi_session
from app.services.vmware.clone import clone_from_template
from app.services.vmware.configure import power_on, reconfigure_vm, wait_for_guest_reboot, wait_for_tools
from app.services.disk_policy import provisioned_disk_gb
from app.services.vmware.disk import expand_vm_disk_if_needed, normalize_disk_gb, vm_disk_gb
from app.services.vmware.guest_ops import (
    extend_windows_c_volume,
    rearm_windows_activation,
    resolve_guest_user,
    set_windows_password,
    set_windows_static_ip,
)
from app.services.vmware.ip_pool import allocate_proxy_slot

logger = logging.getLogger(__name__)


def _notify_vps_failed(db: Session, order: VpsOrder, vm_name: str) -> None:
    from app.services import host_notify

    host_notify.on_provision_failed(
        db,
        kind="VPS",
        summary=vm_name or order.hostname or f"pedido #{order.id}",
        customer_user_id=order.user_id,
        client_url="/dashboard/orders",
    )


class VMwareProvisioner:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def provision_order(self, db: Session, order: VpsOrder) -> VpsInstance:
        """Fluxo completo: clone → reconfig → disco → power on → IP → senha forte."""
        existing = (
            db.query(VpsInstance)
            .filter(VpsInstance.order_id == order.id)
            .first()
        )
        if existing:
            return existing

        vm_name = vm_name_from_hostname(order.hostname)
        assert_hostname_available(db, order.hostname, exclude_order_id=order.id)

        update_order_progress(db, order, progress=10, step="preparing")

        proxy_slot = allocate_proxy_slot(db, self.settings)
        ip = proxy_slot.internal_ip

        plan = order.plan
        plan_default_disk = plan.default_disk_gb if plan else 30
        disk_gb = normalize_disk_gb(order.disk_gb or plan_default_disk, plan_default=plan_default_disk)
        network_mbps = plan.network_mbps if plan else 100
        os_template = getattr(order, "os_template", None) or DEFAULT_OS_TEMPLATE
        template_name = template_name_for_os(os_template)
        template_password = self.settings.guest_password_for_os(os_template)
        if not template_password:
            raise ValueError(
                "Senha do template Windows não configurada. "
                f"Defina GUEST_ADMIN_PASSWORD ou GUEST_ADMIN_PASSWORD_{os_template.upper()} no .env"
            )

        new_password = generate_windows_password()

        instance: VpsInstance | None = None
        instance = VpsInstance(
            user_id=order.user_id,
            order_id=order.id,
            plan_id=order.plan_id,
            vm_name=vm_name,
            vcpu=order.vcpu,
            ram_mb=order.ram_mb,
            disk_gb=disk_gb,
            os_template=os_template,
            network_mbps=network_mbps,
            ip_address=ip,
            status=VpsStatus.CREATING,
            esxi_host=self.settings.esxi_host,
        )
        set_instance_windows_password(instance, new_password)
        db.add(instance)
        update_order_progress(db, order, progress=12, step="copying_disk")

        def on_disk_progress(vmware_percent: int) -> None:
            update_order_progress(
                db,
                order,
                progress=disk_copy_progress(vmware_percent),
                step="copying_disk",
            )

        try:
            with esxi_session(self.settings) as client:
                logger.info("Clonando template %s → %s", template_name, vm_name)
                vm = clone_from_template(
                    client,
                    template_name=template_name,
                    new_vm_name=vm_name,
                    datastore_name=self.settings.esxi_datastore,
                    power_on=False,
                    on_disk_progress=on_disk_progress,
                )
                instance.vm_moid = vm._moId
                instance.status = VpsStatus.CONFIGURING
                update_order_progress(db, order, progress=62, step="registering")
                db.commit()

                cloned_disk_gb = vm_disk_gb(vm)
                hypervisor_disk_gb = provisioned_disk_gb(disk_gb)
                logger.info(
                    "Disco do clone %s: %s GB (contratado: %s GB, provisionado: %s GB)",
                    vm_name,
                    cloned_disk_gb,
                    disk_gb,
                    hypervisor_disk_gb,
                )

                update_order_progress(db, order, progress=68, step="configuring")
                reconfigure_vm(client, vm, order.vcpu, order.ram_mb)

                disk_extended = expand_vm_disk_if_needed(client, vm, hypervisor_disk_gb)
                if disk_extended:
                    logger.info(
                        "Disco expandido de %s GB para %s GB",
                        cloned_disk_gb,
                        hypervisor_disk_gb,
                    )

                update_order_progress(db, order, progress=74, step="powering_on")
                power_on(client, vm)

                update_order_progress(db, order, progress=78, step="waiting_tools")

                def on_tools_tick(elapsed: int, total: int) -> None:
                    pct = 78 + min(8, int(elapsed / max(total, 1) * 8))
                    update_order_progress(db, order, progress=pct, step="waiting_tools")

                vm = wait_for_tools(
                    client,
                    vm,
                    timeout=600,
                    on_tick=on_tools_tick,
                    tools_stuck_timeout=300,
                )

                update_order_progress(db, order, progress=86, step="waiting_auth")

                def on_auth_tick(elapsed: int, total: int) -> None:
                    pct = 86 + min(4, int(elapsed / max(total, 1) * 4))
                    update_order_progress(db, order, progress=pct, step="waiting_auth")

                guest_user = resolve_guest_user(
                    client,
                    vm,
                    self.settings,
                    password=template_password,
                    template_name=template_name,
                    on_tick=on_auth_tick,
                )
                update_order_progress(db, order, progress=90, step="starting_os")

                update_order_progress(db, order, progress=92, step="configuring_network")
                set_windows_static_ip(
                    client,
                    vm,
                    self.settings,
                    ip,
                    password=template_password,
                    template_name=template_name,
                    guest_user=guest_user,
                )

                if disk_extended:
                    extend_windows_c_volume(
                        client,
                        vm,
                        self.settings,
                        password=template_password,
                        template_name=template_name,
                        guest_user=guest_user,
                    )

                update_order_progress(db, order, progress=96, step="configuring")
                set_windows_password(
                    client,
                    vm,
                    self.settings,
                    guest_user,
                    new_password,
                    current_password=template_password,
                    template_name=template_name,
                )

                update_order_progress(db, order, progress=97, step="rearming_windows")
                try:
                    reboot_needed = rearm_windows_activation(
                        client,
                        vm,
                        self.settings,
                        guest_user,
                        password=new_password,
                        template_name=template_name,
                    )
                    if reboot_needed:
                        update_order_progress(db, order, progress=98, step="rebooting")
                        vm = wait_for_guest_reboot(client, vm, timeout=600)
                except TimeoutError as exc:
                    # Rearm / guest process lento não impede a VPS de ficar utilizável.
                    logger.warning(
                        "Rearm Windows em %s ignorado (não crítico): %s",
                        vm_name,
                        exc,
                    )
                except Exception as exc:
                    logger.warning(
                        "Rearm Windows em %s falhou (não crítico): %s",
                        vm_name,
                        exc,
                    )

            paid_until, billing_day = initial_paid_until(instance.created_at)
            instance.paid_until = paid_until
            instance.billing_day = billing_day
            instance.suspended_for_billing = False
            instance.status = VpsStatus.RUNNING
            order.status = OrderStatus.ACTIVE
            order.error_message = None
            instance.error_message = None
            update_order_progress(db, order, progress=100, step="ready")
            db.commit()
            db.refresh(instance)
            from app.services import host_notify

            host_notify.on_provision_ready(
                db,
                kind="VPS",
                summary=vm_name,
                customer_user_id=order.user_id,
                client_url="/dashboard",
            )

            try:
                from app.services.port_proxy import rename_proxy_page

                rename_proxy_page(proxy_slot.proxy_page, vm_name, settings=self.settings)
            except Exception as exc:
                logger.warning(
                    "VPS %s criada, mas falhou renomear página %s no Proxy Manager: %s",
                    vm_name,
                    proxy_slot.proxy_page,
                    exc,
                )

            return instance

        except ValueError as exc:
            message = str(exc)
            logger.error("Falha ao provisionar VPS %s: %s", vm_name, message)
            if instance is not None:
                instance.status = VpsStatus.ERROR
                instance.error_message = message
            order.status = OrderStatus.FAILED
            order.error_message = message
            update_order_progress(db, order, progress=order.provision_progress, step="failed")
            db.commit()
            _notify_vps_failed(db, order, vm_name)
            raise
        except TimeoutError as exc:
            message = str(exc)
            logger.error("Falha ao provisionar VPS %s: %s", vm_name, message)
            if instance is not None:
                instance.status = VpsStatus.ERROR
                instance.error_message = message
            order.status = OrderStatus.FAILED
            order.error_message = message
            update_order_progress(db, order, progress=order.provision_progress, step="failed")
            db.commit()
            _notify_vps_failed(db, order, vm_name)
            raise
        except Exception as exc:
            logger.exception("Falha ao provisionar VPS %s", vm_name)
            message = str(exc)
            if instance is not None:
                instance.status = VpsStatus.ERROR
                instance.error_message = message
            order.status = OrderStatus.FAILED
            order.error_message = message
            update_order_progress(db, order, progress=order.provision_progress, step="failed")
            db.commit()
            _notify_vps_failed(db, order, vm_name)
            raise

