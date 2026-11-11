"""Reconfiguração de recursos e energia da VM."""

from __future__ import annotations

from collections.abc import Callable

from pyVmomi import vim

from app.services.vmware.client import ESXiClient
from app.services.vmware.tools_status import TOOLS_MISSING_MESSAGE, is_vmware_tools_missing


def _find_cdrom(vm: vim.VirtualMachine) -> vim.vm.device.VirtualCdrom | None:
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualCdrom):
            return device
    return None


def disconnect_cdrom_iso(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    """Tira ISO do CD para o ESXi poder montar o instalador do VMware Tools."""
    cdrom = _find_cdrom(vm)
    if cdrom is None:
        return
    if not isinstance(cdrom.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo):
        return
    cdrom.backing = vim.vm.device.VirtualCdrom.RemoteAtapiBackingInfo()
    cdrom.backing.deviceName = ""
    if cdrom.connectable:
        cdrom.connectable.connected = False
        cdrom.connectable.startConnected = False
    spec = vim.vm.ConfigSpec()
    change = vim.vm.device.VirtualDeviceSpec()
    change.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    change.device = cdrom
    spec.deviceChange = [change]
    task = vm.ReconfigVM_Task(spec=spec)
    client.wait_for_task(task)


def ensure_ide_cdrom(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    if _find_cdrom(vm) is not None:
        return
    ide = None
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualIDEController):
            if getattr(device, "busNumber", 0) == 1:
                ide = device
                break
            if ide is None:
                ide = device
    if ide is None:
        raise RuntimeError(f"VM '{vm.name}' não tem controlador IDE para o CD do Tools")
    cdrom = vim.vm.device.VirtualCdrom()
    cdrom.key = -1
    cdrom.controllerKey = ide.key
    cdrom.unitNumber = 0
    cdrom.backing = vim.vm.device.VirtualCdrom.RemoteAtapiBackingInfo()
    cdrom.backing.deviceName = ""
    cdrom.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    cdrom.connectable.allowGuestControl = True
    cdrom.connectable.startConnected = False
    cdrom.connectable.connected = False
    spec = vim.vm.ConfigSpec()
    change = vim.vm.device.VirtualDeviceSpec()
    change.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    change.device = cdrom
    spec.deviceChange = [change]
    task = vm.ReconfigVM_Task(spec=spec)
    client.wait_for_task(task)


def mount_vmware_tools_installer(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
        raise RuntimeError(f"Ligue '{vm.name}' para montar o instalador do agente")
    moid = vm._moId
    ensure_ide_cdrom(client, vm)
    vm = client.find_vm_by_moid(moid) or vm
    disconnect_cdrom_iso(client, vm)
    vm = client.find_vm_by_moid(moid) or vm
    try:
        vm.MountToolsInstaller()
    except vim.fault.InvalidState:
        pass


def extend_virtual_disk(client: ESXiClient, vm: vim.VirtualMachine, new_size_gb: int) -> None:
    """Aumenta o primeiro disco virtual para pelo menos new_size_gb."""
    new_size_kb = new_size_gb * 1024 * 1024

    disk = None
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualDisk):
            disk = device
            break
    if disk is None:
        raise ValueError("Disco virtual não encontrado na VM")

    if new_size_kb <= disk.capacityInKB:
        return

    spec = vim.vm.ConfigSpec()
    dev_spec = vim.vm.device.VirtualDeviceSpec()
    dev_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    dev_spec.device = disk
    dev_spec.device.capacityInKB = new_size_kb
    spec.deviceChange = [dev_spec]
    task = vm.ReconfigVM_Task(spec=spec)
    client.wait_for_task(task)


def _is_powered_on(vm: vim.VirtualMachine) -> bool:
    return vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn


def reconfigure_vm(client: ESXiClient, vm: vim.VirtualMachine, vcpu: int, ram_mb: int) -> None:
    """Altera vCPU e RAM da VM via vim.VirtualMachine.ReconfigVM_Task()."""
    spec = vim.vm.ConfigSpec()
    spec.numCPUs = vcpu
    spec.memoryMB = ram_mb
    task = vm.ReconfigVM_Task(spec=spec)
    client.wait_for_task(task)


def apply_resource_upgrade(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    *,
    vcpu: int | None = None,
    ram_mb: int | None = None,
    disk_gb: int | None = None,
) -> bool:
    """
    Aplica upgrade de vCPU/RAM/disco.
    Desliga a VM antes de alterar CPU/RAM (hot-plug desabilitado no template).
    Retorna True se a VM estava ligada antes do upgrade.
    """
    was_on = _is_powered_on(vm)
    needs_hw = vcpu is not None or ram_mb is not None

    if needs_hw and was_on:
        power_off(client, vm)

    if needs_hw:
        spec = vim.vm.ConfigSpec()
        if vcpu is not None:
            spec.numCPUs = vcpu
        if ram_mb is not None:
            spec.memoryMB = ram_mb
        task = vm.ReconfigVM_Task(spec=spec)
        client.wait_for_task(task)

    if disk_gb is not None:
        extend_virtual_disk(client, vm, disk_gb)

    if needs_hw and was_on:
        power_on(client, vm)

    return was_on


def power_on(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        return
    task = vm.PowerOn()
    client.wait_for_task(task, timeout=300)


def power_off(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        task = vm.PowerOff()
        client.wait_for_task(task, timeout=120)


def reset_vm(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    """Reinício forçado (hard reset) se ligada; liga se estiver desligada."""
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        task = vm.ResetVM_Task()
        client.wait_for_task(task, timeout=120)
    else:
        power_on(client, vm)


def destroy_vm(client: ESXiClient, vm: vim.VirtualMachine) -> None:
    power_off(client, vm)
    task = vm.Destroy_Task()
    client.wait_for_task(task, timeout=300)


def wait_for_guest_reboot(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    timeout: int = 600,
    reboot_start_timeout: int = 120,
) -> vim.VirtualMachine:
    """
    Aguarda reinício do guest após shutdown /r.
    Detecta queda do Tools e volta a aguardar VMware Tools pronto.
    """
    import logging
    import time

    log = logging.getLogger(__name__)
    moid = vm._moId
    start = time.time()
    reboot_started = False

    while time.time() - start < reboot_start_timeout:
        fresh = client.find_vm_by_moid(moid)
        if fresh is not None:
            vm = fresh
        guest = vm.guest
        if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
            reboot_started = True
            log.info("Reinício detectado em %s (VM desligada)", vm.name)
            break
        if guest and guest.guestState == vim.vm.GuestInfo.GuestState.notRunning:
            reboot_started = True
            log.info("Reinício detectado em %s (guest notRunning)", vm.name)
            break
        if guest and guest.toolsStatus != vim.vm.GuestInfo.ToolsStatus.toolsOk:
            reboot_started = True
            log.info("Reinício detectado em %s (Tools indisponível)", vm.name)
            break
        time.sleep(3)

    if not reboot_started:
        log.warning(
            "Reinício não detectado em %s dentro de %ss; aguardando Tools mesmo assim",
            vm.name,
            reboot_start_timeout,
        )

    elapsed = int(time.time() - start)
    remaining = max(60, timeout - elapsed)
    return wait_for_tools(client, vm, timeout=remaining)


def wait_for_tools(
    client: ESXiClient,
    vm: vim.VirtualMachine,
    timeout: int = 300,
    *,
    on_tick: Callable[[int, int], None] | None = None,
    tools_stuck_timeout: int = 300,
    tools_missing_timeout: int = 90,
) -> vim.VirtualMachine:
    """
    Aguarda VMware Tools e guest operations ficarem prontos.
    Atualiza o objeto VM a cada poll (evita estado stale no pyVmomi).
    """
    import logging
    import time

    log = logging.getLogger(__name__)
    moid = vm._moId
    start = time.time()
    tools_ok_since: float | None = None
    grace_after_tools_s = 45
    powered_on_since: float | None = None

    while time.time() - start < timeout:
        fresh = client.find_vm_by_moid(moid)
        if fresh is not None:
            vm = fresh
        guest = vm.guest
        elapsed = int(time.time() - start)
        if on_tick is not None:
            on_tick(elapsed, timeout)

        if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
            if powered_on_since is None:
                powered_on_since = time.time()
        else:
            powered_on_since = None

        tools_running = (
            guest
            and guest.toolsStatus == vim.vm.GuestInfo.ToolsStatus.toolsOk
            and guest.toolsRunningStatus == vim.vm.GuestInfo.ToolsRunningStatus.guestToolsRunning
        )
        if tools_running:
            if tools_ok_since is None:
                tools_ok_since = time.time()
                log.info("VMware Tools OK em %s; aguardando guest operations...", vm.name)
            ops_ready = getattr(guest, "guestOperationsReady", None)
            guest_host = (guest.hostName or "").strip()
            guest_id = guest.guestId
            windows_ready = bool(guest_host or guest_id)
            if ops_ready is True and windows_ready:
                log.info("Guest operations prontas em %s (host=%s)", vm.name, guest_host or guest_id)
                return vm
            if tools_ok_since and time.time() - tools_ok_since >= grace_after_tools_s:
                log.info(
                    "Guest operations grace period (%ss) concluído em %s",
                    grace_after_tools_s,
                    vm.name,
                )
                return vm
        else:
            tools_ok_since = None
            if powered_on_since:
                on_for = time.time() - powered_on_since
                if on_for >= tools_missing_timeout and is_vmware_tools_missing(guest):
                    raise TimeoutError(TOOLS_MISSING_MESSAGE)
                if (
                    on_for >= tools_stuck_timeout
                    and guest
                    and guest.toolsStatus == vim.vm.GuestInfo.ToolsStatus.toolsNotRunning
                    and not is_vmware_tools_missing(guest)
                ):
                    raise TimeoutError(
                        "O Windows ligou, mas ainda não está pronto para configuração automática. "
                        "Tente novamente daqui a alguns minutos ou fale com o suporte."
                    )
        time.sleep(5)
    raise TimeoutError(
        "O Windows não ficou pronto a tempo para a configuração automática. "
        "Se a tela já aparece no console, aguarde o desktop e tente de novo, ou fale com o suporte."
    )
