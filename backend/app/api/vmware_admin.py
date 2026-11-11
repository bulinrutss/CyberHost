"""Endpoints administrativos para diagnóstico VMware."""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_admin
from app.config import get_settings
from app.models.user import User
from app.services.vmware.client import esxi_session
from app.services.vmware.guest_ops import guest_network_debug

router = APIRouter()


@router.get("/health")
def vmware_health(user: User = Depends(get_current_admin)):
    """Verifica conexão com ESXi e recursos necessários."""
    try:
        with esxi_session() as client:
            return client.health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Host indisponível") from exc


@router.get("/vms")
def list_esxi_vms(user: User = Depends(get_current_admin)):
    """Lista VMs no host ESXi (para debug)."""
    with esxi_session() as client:
        return {"vms": client.list_vms()}


@router.get("/guest-debug/{vm_name}")
def vmware_guest_debug(vm_name: str, user: User = Depends(get_current_admin)):
    """Diagnóstico de credenciais e rede no guest Windows (Guest Operations)."""
    settings = get_settings()
    with esxi_session(settings) as client:
        vm = client.find_vm_by_name(vm_name)
        if vm is None:
            raise HTTPException(status_code=404, detail=f"VM '{vm_name}' não encontrada")
        return guest_network_debug(client, vm, settings)
