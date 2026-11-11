"""Operações de clone de VM no ESXi."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pyVmomi import vim

from app.console_io import safe_print
from app.services.vmware.client import ESXiClient
from app.services.vmware.tools_status import assert_template_has_vmware_tools

logger = logging.getLogger(__name__)


def _get_datacenter(content: vim.ServiceInstanceContent) -> vim.Datacenter:
    for child in content.rootFolder.childEntity:
        if isinstance(child, vim.Datacenter):
            return child
    raise RuntimeError("Infraestrutura indisponível. Fale com o suporte.")


def _is_standalone_esxi(content: vim.ServiceInstanceContent) -> bool:
    return content.about.apiType == "HostAgent"


def _build_config_spec(
    template: vim.VirtualMachine,
    new_vm_name: str,
    datastore_name: str,
    copied_disks: list[tuple[vim.vm.device.VirtualDisk, str]],
) -> vim.vm.ConfigSpec:
    config = vim.vm.ConfigSpec()
    config.name = new_vm_name
    config.guestId = template.config.guestId
    config.version = template.config.version
    config.numCPUs = template.config.hardware.numCPU
    config.memoryMB = template.config.hardware.memoryMB
    config.firmware = template.config.firmware
    config.files = vim.vm.FileInfo()
    config.files.vmPathName = f"[{datastore_name}] {new_vm_name}/{new_vm_name}.vmx"

    device_changes: list[vim.vm.device.VirtualDeviceSpec] = []

    scsi_spec = vim.vm.device.VirtualDeviceSpec()
    scsi_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    scsi = vim.vm.device.VirtualLsiLogicSASController()
    scsi.key = 1000
    scsi.busNumber = 0
    scsi.sharedBus = vim.VirtualSCSISharing.noSharing
    scsi_spec.device = scsi
    device_changes.append(scsi_spec)

    for template_disk, disk_path in copied_disks:
        disk_spec = vim.vm.device.VirtualDeviceSpec()
        disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        # Disco já copiado — anexa o arquivo existente sem criar um novo
        disk = vim.vm.device.VirtualDisk()
        disk.controllerKey = 1000
        disk.unitNumber = template_disk.unitNumber
        disk.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        disk.backing.fileName = disk_path
        disk.backing.diskMode = template_disk.backing.diskMode
        disk.capacityInKB = template_disk.capacityInKB
        disk_spec.device = disk
        device_changes.append(disk_spec)

    for device in template.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            nic_spec = vim.vm.device.VirtualDeviceSpec()
            nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            nic = type(device)()
            nic.addressType = "generated"
            nic.wakeOnLanEnabled = getattr(device, "wakeOnLanEnabled", True)
            nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nic.backing.deviceName = device.backing.deviceName
            nic.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            nic.connectable.startConnected = True
            nic.connectable.allowGuestControl = True
            nic_spec.device = nic
            device_changes.append(nic_spec)
            break

    config.deviceChange = device_changes
    return config


def _clone_standalone_esxi(
    client: ESXiClient,
    template: vim.VirtualMachine,
    new_vm_name: str,
    datastore_name: str,
    power_on: bool,
    on_disk_progress: Callable[[int], None] | None = None,
) -> vim.VirtualMachine:
    """
    Clone em ESXi standalone (sem vCenter).

    VirtualMachine.Clone() não é suportado no HostAgent — copiamos o disco
    e registramos uma nova VM via CreateVM_Task.
    """
    content = client.content
    datacenter = _get_datacenter(content)
    vm_folder = datacenter.vmFolder
    pool = template.resourcePool or client.get_default_resource_pool()

    dest_dir = f"[{datastore_name}] {new_vm_name}"
    try:
        content.fileManager.MakeDirectory(
            name=dest_dir,
            datacenter=datacenter,
            createParentDirectories=True,
        )
    except vim.fault.FileAlreadyExists:
        pass

    template_disks = [
        d for d in template.config.hardware.device if isinstance(d, vim.vm.device.VirtualDisk)
    ]
    if not template_disks:
        raise ValueError(f"Template '{template.name}' não possui discos virtuais")

    copied_disks: list[tuple[vim.vm.device.VirtualDisk, str]] = []
    for index, disk in enumerate(template_disks):
        suffix = "" if index == 0 else f"-{index}"
        dest_disk = f"[{datastore_name}] {new_vm_name}/{new_vm_name}{suffix}.vmdk"

        msg = f"Copiando disco {index + 1}/{len(template_disks)} (pode levar vários minutos)..."
        logger.info(msg)
        safe_print(msg)

        dest_spec = vim.VirtualDiskManager.VirtualDiskSpec()
        dest_spec.adapterType = vim.VirtualDiskManager.VirtualDiskAdapterType.lsiLogic
        dest_spec.diskType = vim.VirtualDiskManager.VirtualDiskType.thin

        task = content.virtualDiskManager.CopyVirtualDisk_Task(
            sourceName=disk.backing.fileName,
            sourceDatacenter=datacenter,
            destName=dest_disk,
            destDatacenter=datacenter,
            destSpec=dest_spec,
            force=False,
        )
        try:
            client.wait_for_task(
                task,
                timeout=3600,
                label=f"Cópia disco {index + 1}",
                on_progress=on_disk_progress,
            )
        except vim.fault.FileAlreadyExists:
            logger.info("Disco %s já existe, reutilizando", dest_disk)
            safe_print(f"Disco já existe, reutilizando: {dest_disk}")
        copied_disks.append((disk, dest_disk))

    msg = "Registrando nova VM no inventário..."
    logger.info(msg)
    safe_print(msg)
    config = _build_config_spec(template, new_vm_name, datastore_name, copied_disks)
    task = vm_folder.CreateVM_Task(config=config, pool=pool)
    task_info = client.wait_for_task(task, timeout=600, label="CreateVM")
    vm = task_info.result

    if power_on:
        power_task = vm.PowerOn()
        client.wait_for_task(power_task, timeout=300)

    return vm


def _clone_via_vcenter(
    client: ESXiClient,
    template: vim.VirtualMachine,
    new_vm_name: str,
    datastore_name: str,
    power_on: bool,
    on_disk_progress: Callable[[int], None] | None = None,
) -> vim.VirtualMachine:
    content = client.content
    datastore = client.get_datastore(datastore_name)
    if datastore is None:
        raise ValueError(f"Datastore '{datastore_name}' não encontrado")

    datacenter = _get_datacenter(content)
    relospec = vim.vm.RelocateSpec()
    relospec.datastore = datastore
    relospec.pool = template.resourcePool or client.get_default_resource_pool()

    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec
    clonespec.powerOn = power_on
    clonespec.template = False

    dest_folder = datacenter.vmFolder
    task = template.Clone(folder=dest_folder, name=new_vm_name, spec=clonespec)
    client.wait_for_task(task, timeout=1800, label="Clone", on_progress=on_disk_progress)

    vm = client.find_vm_by_name(new_vm_name)
    if vm is None:
        raise RuntimeError(f"Clone concluído mas VM '{new_vm_name}' não encontrada")
    return vm


def clone_from_template(
    client: ESXiClient,
    template_name: str,
    new_vm_name: str,
    datastore_name: str,
    power_on: bool = False,
    on_disk_progress: Callable[[int], None] | None = None,
) -> vim.VirtualMachine:
    """
    Clona uma VM template para uma nova VM (full clone).

    No ESXi standalone usa cópia de disco + CreateVM_Task.
    Com vCenter usa VirtualMachine.Clone().
    """
    content = client.content
    template = client.find_vm_by_name(template_name)
    if template is None:
        raise ValueError(f"Imagem '{template_name}' não encontrada")

    assert_template_has_vmware_tools(template)

    if template.runtime.powerState != vim.VirtualMachinePowerState.poweredOff:
        raise ValueError(f"Template '{template_name}' deve estar desligado para clonar")

    if _is_standalone_esxi(content):
        return _clone_standalone_esxi(
            client, template, new_vm_name, datastore_name, power_on, on_disk_progress
        )

    return _clone_via_vcenter(
        client, template, new_vm_name, datastore_name, power_on, on_disk_progress
    )
