"""Console HTML5 (WebMKS) para VMs no ESXi."""

from __future__ import annotations

from fastapi import HTTPException
from pyVmomi import vim

from app.config import get_settings
from app.models.vps import VpsInstance
from app.services.vmware.client import esxi_session


def _resolve_vm(client, instance: VpsInstance) -> vim.VirtualMachine:
    vm = client.find_vm_by_name(instance.vm_name)
    if vm is None and instance.vm_moid:
        vm = client.find_vm_by_moid(instance.vm_moid)
    if vm is None:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    return vm


def acquire_webmks_ticket(instance: VpsInstance) -> tuple[str, int, str, str]:
    """Retorna (host, port, ticket, wss_url) para conexão WebMKS no ESXi."""
    settings = get_settings()
    with esxi_session() as client:
        vm = _resolve_vm(client, instance)
        if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
            raise HTTPException(
                status_code=400,
                detail="Ligue o servidor para abrir o console.",
            )
        try:
            ticket_obj = vm.AcquireTicket(ticketType="webmks")
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Não foi possível obter ticket do console: {exc}",
            ) from exc

        host = (settings.esxi_host or instance.esxi_host or ticket_obj.host or "").strip()
        port = int(ticket_obj.port or settings.esxi_port or 443)
        ticket = (ticket_obj.ticket or "").strip()
        if not host or not ticket:
            raise HTTPException(status_code=502, detail="Ticket do console inválido")

        wss_url = f"wss://{host}:{port}/ticket/{ticket}"
        return host, port, ticket, wss_url
