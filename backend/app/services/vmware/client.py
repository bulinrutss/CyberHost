"""Cliente de conexão com VMware ESXi via pyVmomi (vSphere Web Services API)."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Callable
from typing import Generator

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

from app.config import Settings, get_settings
from app.console_io import safe_print
from app.esxi_tls import build_esxi_ssl_context


class ESXiClient:
    """
    Conecta ao ESXi 6.7 standalone usando a vSphere Web Services API (SOAP).

    Documentação: docs/VMWARE_INTEGRATION.md
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._si: vim.ServiceInstance | None = None

    def connect(self) -> vim.ServiceInstance:
        if self._si is not None:
            return self._si

        context = build_esxi_ssl_context(self.settings)

        self._si = SmartConnect(
            host=self.settings.esxi_host,
            user=self.settings.esxi_user,
            pwd=self.settings.esxi_password,
            port=self.settings.esxi_port,
            sslContext=context,
        )
        return self._si

    def disconnect(self) -> None:
        if self._si is not None:
            Disconnect(self._si)
            self._si = None

    @property
    def content(self) -> vim.ServiceInstanceContent:
        return self.connect().RetrieveContent()

    def find_vm_by_moid(self, moid: str) -> vim.VirtualMachine | None:
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm in container.view:
                if vm._moId == moid:
                    return vm
        finally:
            container.Destroy()
        return None

    def find_vm_by_name(self, name: str) -> vim.VirtualMachine | None:
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm in container.view:
                if vm.name == name:
                    return vm
        finally:
            container.Destroy()
        return None

    def list_vms(self) -> list[dict]:
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            result = []
            for vm in container.view:
                summary = vm.summary
                result.append(
                    {
                        "name": vm.name,
                        "moid": vm._moId,
                        "power_state": str(summary.runtime.powerState),
                        "cpu": summary.config.numCpu,
                        "ram_mb": summary.config.memorySizeMB,
                        "guest_os": summary.config.guestFullName,
                        "ip": summary.guest.ipAddress,
                    }
                )
            return result
        finally:
            container.Destroy()

    def get_datastore(self, name: str) -> vim.Datastore | None:
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.Datastore], True
        )
        try:
            for ds in container.view:
                if ds.name == name:
                    return ds
        finally:
            container.Destroy()
        return None

    def get_network(self, name: str) -> vim.Network | None:
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.Network], True
        )
        try:
            for net in container.view:
                if net.name == name:
                    return net
        finally:
            container.Destroy()
        return None

    def get_default_resource_pool(self) -> vim.ResourcePool:
        """Resource pool padrão do host ESXi standalone."""
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.ComputeResource], True
        )
        try:
            for compute in container.view:
                return compute.resourcePool
        finally:
            container.Destroy()
        raise RuntimeError("Infraestrutura indisponível. Fale com o suporte.")

    def wait_for_task(
        self,
        task: vim.Task,
        timeout: int = 600,
        label: str | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> vim.TaskInfo:
        """Aguarda conclusão de uma task do vSphere."""
        import logging
        import time

        log = logging.getLogger(__name__)
        start = time.time()
        last_progress = -1
        while True:
            info = task.info
            state = info.state
            if label and info.progress is not None and info.progress != last_progress:
                last_progress = info.progress
                msg = f"{label}: {info.progress}%"
                log.info(msg)
                safe_print(msg)
                if on_progress:
                    on_progress(info.progress)
            if state == vim.TaskInfo.State.success:
                if label:
                    log.info("%s: concluído", label)
                    safe_print(f"{label}: concluído")
                return info
            if state == vim.TaskInfo.State.error:
                raise info.error
            if time.time() - start > timeout:
                raise TimeoutError(f"Task excedeu timeout de {timeout}s")
            time.sleep(2)

    def health_check(self) -> dict:
        """Verifica conectividade e inventário básico."""
        from app.services.os_templates import list_os_templates

        content = self.content
        datastore = self.get_datastore(self.settings.esxi_datastore)
        network = self.get_network(self.settings.esxi_network)

        templates = []
        all_found = True
        for spec in list_os_templates():
            vm = self.find_vm_by_name(spec.template_name)
            found = vm is not None
            if not found:
                all_found = False
            guest = vm.guest if vm else None
            tools_version = 0
            try:
                tools_version = int(getattr(guest, "toolsVersion", 0) or 0) if guest else 0
            except (TypeError, ValueError):
                tools_version = 0
            status = str(getattr(guest, "toolsStatus", "") or "")
            tools_installed = bool(guest) and tools_version > 0 and "notinstalled" not in status.lower()
            templates.append(
                {
                    "slug": spec.slug,
                    "label": spec.label,
                    "template_name": spec.template_name,
                    "found": found,
                    "is_recommended": spec.is_recommended,
                    "tools_installed": tools_installed,
                    "tools_version": tools_version,
                }
            )

        legacy = self.find_vm_by_name(self.settings.esxi_template_name)

        guest_auth: list[dict] = []
        for spec in list_os_templates():
            vm = self.find_vm_by_name(spec.template_name)
            if not vm or vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
                guest_auth.append(
                    {
                        "template": spec.template_name,
                        "slug": spec.slug,
                        "checked": False,
                        "reason": "template desligado ou ausente",
                    }
                )
                continue
            guest = vm.guest
            guest_host = (guest.hostName or "").strip() if guest else ""
            guest_meta = {
                "guest_host_name": guest_host or None,
                "guest_id": guest.guestId if guest else None,
            }
            if not guest or guest.toolsStatus != vim.vm.GuestInfo.ToolsStatus.toolsOk:
                guest_auth.append(
                    {
                        "template": spec.template_name,
                        "slug": spec.slug,
                        "checked": False,
                        "reason": "agente do Windows indisponível",
                        **guest_meta,
                    }
                )
                continue
            if not guest_host:
                guest_auth.append(
                    {
                        "template": spec.template_name,
                        "slug": spec.slug,
                        "checked": True,
                        "ok": False,
                        "reason": (
                            "Windows não reportou o nome do computador (imagem incompleta). "
                            "Abra o console, faça login como Administrador, aguarde o desktop "
                            "e desligue o servidor antes de clonar."
                        ),
                        **guest_meta,
                    }
                )
                continue
            pwd = self.settings.guest_password_for_os(spec.slug)
            auth = vim.NamePasswordAuthentication(
                username=self.settings.guest_admin_user,
                password=pwd,
                interactiveSession=False,
            )
            try:
                self.content.guestOperationsManager.authManager.ValidateCredentials(vm, auth)
                guest_auth.append(
                    {
                        "template": spec.template_name,
                        "slug": spec.slug,
                        "checked": True,
                        "ok": True,
                        **guest_meta,
                    }
                )
            except vim.fault.InvalidGuestLogin:
                guest_auth.append(
                    {
                        "template": spec.template_name,
                        "slug": spec.slug,
                        "checked": True,
                        "ok": False,
                        "reason": "senha rejeitada pelo guest (ajuste GUEST_ADMIN_PASSWORD ou override por SO)",
                        **guest_meta,
                    }
                )

        return {
            "connected": True,
            "host": self.settings.esxi_host,
            "api": "vSphere Web Services (pyVmomi)",
            "product": content.about.fullName,
            "build": content.about.build,
            "template_found": all_found,
            "template_name": self.settings.esxi_template_name,
            "legacy_template_found": legacy is not None,
            "templates": templates,
            "datastore_found": datastore is not None,
            "network_found": network is not None,
            "vm_count": len(self.list_vms()),
            "guest_auth": guest_auth,
        }


@contextmanager
def esxi_session(settings: Settings | None = None) -> Generator[ESXiClient, None, None]:
    client = ESXiClient(settings)
    try:
        client.connect()
        yield client
    finally:
        client.disconnect()
