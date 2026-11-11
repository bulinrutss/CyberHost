"""Explorador de arquivos e shell SSH do host Linux (admin)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models.user import User
from app.schemas.host_files import (
    HostFileContent,
    HostFileEntry,
    HostFileListResponse,
    HostFileWrite,
    HostMkdirRequest,
    HostRenameRequest,
    HostShellTicketResponse,
)
from app.schemas.host_metrics import HostMetricsResponse
from app.services import host_files as host_files_svc
from app.services import host_metrics as host_metrics_svc
from app.services import host_shell as host_shell_svc
from app.services.console_tickets import authenticate_host_shell_websocket, issue_host_shell_ticket

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics", response_model=HostMetricsResponse)
def host_metrics(_: User = Depends(get_current_admin)):
    return host_metrics_svc.collect_host_metrics()


@router.get("/info")
def host_info(_: User = Depends(get_current_admin)):
    settings = get_settings()
    return {
        "roots": [str(path) for path in host_files_svc.allowed_roots(settings)],
        "max_edit_bytes": host_files_svc.max_edit_bytes(settings),
        "max_upload_bytes": host_files_svc.max_upload_bytes(settings),
        "shell_available": host_shell_svc.shell_available(),
        "shell_cwd": settings.host_shell_cwd,
    }


@router.get("/files", response_model=HostFileListResponse)
def list_host_files(
    path: str = "",
    admin: User = Depends(get_current_admin),
):
    listing = host_files_svc.list_directory(path)
    logger.info("admin=%s host list path=%s", admin.id, listing.get("path") or "/")
    return listing


@router.get("/files/content", response_model=HostFileContent)
def read_host_file(
    path: str,
    admin: User = Depends(get_current_admin),
):
    data = host_files_svc.read_file(path)
    logger.info("admin=%s host read path=%s", admin.id, data["path"])
    return data


@router.put("/files/content")
def write_host_file(
    payload: HostFileWrite,
    admin: User = Depends(get_current_admin),
):
    result = host_files_svc.write_file(payload.path, payload.content)
    logger.info("admin=%s host write path=%s", admin.id, result["path"])
    return result


@router.post("/files/mkdir", response_model=HostFileEntry)
def mkdir_host(
    payload: HostMkdirRequest,
    admin: User = Depends(get_current_admin),
):
    return host_files_svc.mkdir(payload.path, payload.name)


@router.post("/files/create", response_model=HostFileEntry)
def create_host_file(
    payload: HostMkdirRequest,
    admin: User = Depends(get_current_admin),
):
    return host_files_svc.create_file(payload.path, payload.name)


@router.post("/files/rename", response_model=HostFileEntry)
def rename_host_file(
    payload: HostRenameRequest,
    admin: User = Depends(get_current_admin),
):
    return host_files_svc.rename_entry(payload.path, payload.new_name)


@router.delete("/files")
def delete_host_file(
    path: str,
    admin: User = Depends(get_current_admin),
):
    host_files_svc.delete_entry(path)
    logger.info("admin=%s host delete path=%s", admin.id, path)
    return {"ok": True}


@router.get("/files/download")
def download_host_file(
    path: str,
    admin: User = Depends(get_current_admin),
):
    target = host_files_svc.download_path(path)
    logger.info("admin=%s host download path=%s", admin.id, target)
    return FileResponse(path=target, filename=target.name, media_type="application/octet-stream")


@router.post("/files/upload", response_model=HostFileEntry)
async def upload_host_file(
    path: str = Query(...),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
):
    result = host_files_svc.upload_file(path, file)
    logger.info("admin=%s host upload path=%s", admin.id, result["path"])
    return result


@router.post("/shell/ticket", response_model=HostShellTicketResponse)
def host_shell_ticket(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not host_shell_svc.shell_available():
        return HostShellTicketResponse(
            ticket="",
            expires_in_seconds=0,
            ws_path="/api/admin/host/shell/ws",
            available=False,
            message="Shell disponível só no Linux de produção.",
        )
    raw, ttl = issue_host_shell_ticket(db, admin)
    return HostShellTicketResponse(
        ticket=raw,
        expires_in_seconds=ttl,
        ws_path="/api/admin/host/shell/ws",
        available=True,
        message=None,
    )


@router.websocket("/shell/ws")
async def host_shell_ws(
    websocket: WebSocket,
    ticket: str | None = None,
    token: str | None = None,
):
    async def reject(message: str, *, code: int = 4401) -> None:
        await websocket.accept()
        await websocket.close(code=code, reason=message[:120])

    if token:
        await reject("Não autorizado")
        return
    if not ticket:
        await reject("Ticket ausente")
        return

    db = SessionLocal()
    try:
        admin = authenticate_host_shell_websocket(db, ticket=ticket, jwt_query=token)
    except HTTPException:
        logger.warning("host shell WS auth falhou")
        await reject("Não autorizado")
        return
    finally:
        db.close()

    await websocket.accept()
    try:
        await host_shell_svc.attach_host_shell(websocket, admin_id=admin.id)
    except HTTPException as exc:
        await websocket.close(code=1011, reason=str(exc.detail)[:120])
    except Exception:
        logger.exception("host shell WS falhou admin=%s", admin.id)
        await websocket.close(code=1011, reason="Falha no shell")
