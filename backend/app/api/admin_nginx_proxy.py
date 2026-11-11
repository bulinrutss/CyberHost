"""Administração de proxies nginx (domínios e redirecionamentos)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.nginx_proxy import (
    NginxProxyEntry,
    NginxProxyManualCreate,
    NginxProxyManualUpdate,
    NginxProxySystemUpdate,
)
from app.services import nginx_proxy_admin as svc

router = APIRouter()


@router.get("/nginx-proxies", response_model=list[NginxProxyEntry])
def list_nginx_proxies(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return svc.list_proxy_entries(db)


@router.post("/nginx-proxies", response_model=NginxProxyEntry, status_code=status.HTTP_201_CREATED)
def create_nginx_proxy(
    payload: NginxProxyManualCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    route = svc.create_manual_route(db, payload)
    entries = svc.list_proxy_entries(db)
    match = next((item for item in entries if item["key"] == f"manual-{route.id}"), None)
    if not match:
        raise RuntimeError("proxy criado mas não listado")
    return match


@router.put("/nginx-proxies/{route_id}", response_model=NginxProxyEntry)
def update_nginx_proxy(
    route_id: int,
    payload: NginxProxyManualUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    route = svc.update_manual_route(db, route_id, payload)
    entries = svc.list_proxy_entries(db)
    match = next((item for item in entries if item["key"] == f"manual-{route.id}"), None)
    if not match:
        raise RuntimeError("proxy atualizado mas não listado")
    return match


@router.delete("/nginx-proxies/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_nginx_proxy(
    route_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    svc.delete_manual_route(db, route_id)


@router.put("/nginx-proxies/system/{kind}/{reference_id}", response_model=NginxProxyEntry)
def update_system_nginx_proxy(
    kind: str,
    reference_id: int,
    payload: NginxProxySystemUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    svc.update_system_proxy(db, kind, reference_id, payload.domain)
    entries = svc.list_proxy_entries(db)
    if kind == "web_site":
        keys = [f"site-{reference_id}-custom"]
    elif kind == "vps_connection":
        keys = [f"vps-{reference_id}"]
    else:
        keys = []
    match = next((item for item in entries if item["key"] in keys), None)
    if not match:
        match = next(
            (
                item
                for item in entries
                if item["kind"] == kind and item["reference_id"] == reference_id
            ),
            None,
        )
    if not match:
        raise RuntimeError("proxy do sistema atualizado mas não listado")
    return match


@router.delete("/nginx-proxies/system/{kind}/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_nginx_proxy(
    kind: str,
    reference_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    svc.delete_system_proxy(db, kind, reference_id)
