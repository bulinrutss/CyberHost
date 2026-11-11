"""Importação de VMs existentes no ESXi."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.import_vms import DiscoverVmsResponse, ImportVmsRequest, ImportVmsResponse
from app.services.vm_import import discover_unregistered_vms, import_vms

router = APIRouter()


@router.get("/discover", response_model=DiscoverVmsResponse)
def discover_vms(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lista VMs VPS-* no ESXi que ainda não estão no painel."""
    return discover_unregistered_vms(db)


@router.post("", response_model=ImportVmsResponse)
def import_discovered_vms(
    payload: ImportVmsRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Vincula VMs existentes a contas já cadastradas no painel."""
    return import_vms(db, [item.model_dump() for item in payload.vms])
