"""Administração de todos os sites hospedados."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.api.web_sites import build_site_detail, require_web_hosting
from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.models.web_site import WebSite, WebSiteStatus
from app.schemas.admin_management import AdminWebSiteDeleteResponse
from app.schemas.web_page import WebPageConfig, WebPageEditorResponse
from app.schemas.web_site_analytics import WebSiteAnalyticsResponse
from app.schemas.web_site import (
    WebDomainUpdate,
    WebFileContent,
    WebFileEntry,
    WebFileMkdir,
    WebFileWrite,
    WebLogsResponse,
    WebSiteAdminDetailResponse,
    WebSiteAdminResponse,
    WebSiteResponse,
)
from app.services.auth_step_up import require_step_up
from app.services.web_page_builder import editor_state, save_avatar, save_page
from app.services.web_site_analytics import ALLOWED_DAYS, collect_stats
from app.services import admin_management as admin_mgmt
from app.services import web_process
from app.services import web_ssl
from app.services.web_domain import domain_in_use, normalize_domain
from app.services.web_files import (
    create_directory,
    delete_path,
    list_directory,
    read_file,
    tree_used_bytes,
    upload_file,
    write_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_web_hosting)])


def _resolve_admin_site(db: Session, site_id: int) -> WebSite:
    site = (
        db.query(WebSite)
        .options(joinedload(WebSite.order))
        .filter(WebSite.id == site_id, WebSite.status != WebSiteStatus.DELETED)
        .first()
    )
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return site


def _with_owner(detail, user: User) -> dict:
    payload = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
    payload["user_id"] = user.id
    payload["user_phone"] = user.phone
    payload["user_name"] = user.name
    return payload


@router.get("/web-sites", response_model=list[WebSiteAdminResponse])
def list_all_web_sites(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WebSite, User)
        .join(User, WebSite.user_id == User.id)
        .filter(WebSite.status != WebSiteStatus.DELETED)
        .order_by(WebSite.created_at.desc())
        .all()
    )
    return [
        WebSiteAdminResponse(**_with_owner(build_site_detail(db, site), user))
        for site, user in rows
    ]


@router.get("/web-sites/{site_id}", response_model=WebSiteAdminDetailResponse)
def get_admin_web_site(
    site_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    owner = db.get(User, site.user_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    web_process.sync_site_status(site)
    db.commit()
    detail = build_site_detail(db, site, used=tree_used_bytes(site))
    return WebSiteAdminDetailResponse(**_with_owner(detail, owner))


@router.delete("/web-sites/{site_id}", response_model=AdminWebSiteDeleteResponse)
def admin_delete_web_site(
    site_id: int,
    admin: User = Depends(get_current_admin),
    _: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    return admin_mgmt.delete_web_site(db, admin, site_id)


@router.post("/web-sites/{site_id}/start", response_model=WebSiteResponse)
def admin_start_web_site(
    site_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    try:
        web_process.start_site(site)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    return build_site_detail(db, site)


@router.post("/web-sites/{site_id}/stop", response_model=WebSiteResponse)
def admin_stop_web_site(
    site_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    web_process.stop_site(site)
    db.commit()
    return build_site_detail(db, site)


@router.post("/web-sites/{site_id}/restart", response_model=WebSiteResponse)
def admin_restart_web_site(
    site_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    web_process.stop_site(site)
    try:
        web_process.start_site(site)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    return build_site_detail(db, site)


@router.put("/web-sites/{site_id}/domain", response_model=WebSiteResponse)
def admin_update_web_site_domain(
    site_id: int,
    payload: WebDomainUpdate,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    domain_raw = (payload.domain or "").strip()
    if domain_raw:
        domain = normalize_domain(domain_raw)
        if domain_in_use(db, domain, ignore_site_id=site.id):
            raise HTTPException(status_code=400, detail="Este domínio já está em uso")
        site.domain = domain
    else:
        site.domain = None
    try:
        ssl_ok, ssl_err = web_ssl.configure_domain_with_status(site, db=db)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    if domain_raw and not ssl_ok:
        raise HTTPException(
            status_code=400,
            detail=ssl_err
            or "Domínio salvo, mas o certificado SSL não foi emitido. "
            "Confira o DNS e, no Cloudflare, use Somente DNS (nuvem cinza) e tente de novo.",
        )
    return build_site_detail(db, site)


@router.get("/web-sites/{site_id}/logs", response_model=WebLogsResponse)
def admin_web_site_logs(
    site_id: int,
    tail: int = Query(default=100, ge=10, le=500),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return WebLogsResponse(lines=web_process.tail_logs(site.data_path, tail), tail=tail)


@router.get("/web-sites/{site_id}/files")
def admin_web_site_files(
    site_id: int,
    path: str = Query(default=""),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return list_directory(site, path)


@router.get("/web-sites/{site_id}/files/content", response_model=WebFileContent)
def admin_web_site_file_content(
    site_id: int,
    path: str,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return read_file(site, path)


@router.put("/web-sites/{site_id}/files/content")
def admin_web_site_file_write(
    site_id: int,
    payload: WebFileWrite,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    write_file(site, payload.path, payload.content)
    return {"ok": True}


@router.post("/web-sites/{site_id}/files/mkdir", response_model=WebFileEntry)
def admin_web_site_file_mkdir(
    site_id: int,
    payload: WebFileMkdir,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return create_directory(site, payload.path, payload.name)


@router.post("/web-sites/{site_id}/files/upload")
def admin_web_site_file_upload(
    site_id: int,
    path: str = Query(default=""),
    file: UploadFile = File(...),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return upload_file(site, path, file)


@router.delete("/web-sites/{site_id}/files")
def admin_web_site_file_delete(
    site_id: int,
    path: str = Query(..., min_length=1),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    delete_path(site, path)
    return {"ok": True}


@router.get("/web-sites/{site_id}/page", response_model=WebPageEditorResponse)
def admin_get_site_page_editor(
    site_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    return editor_state(site)


@router.put("/web-sites/{site_id}/page", response_model=WebPageEditorResponse)
def admin_save_site_page_editor(
    site_id: int,
    payload: WebPageConfig,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    save_page(site, payload)
    db.commit()
    return editor_state(site)


@router.post("/web-sites/{site_id}/page/avatar", response_model=WebPageEditorResponse)
def admin_upload_site_page_avatar(
    site_id: int,
    file: UploadFile = File(...),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    save_avatar(site, file)
    db.commit()
    return editor_state(site)


@router.get("/web-sites/{site_id}/analytics", response_model=WebSiteAnalyticsResponse)
def admin_web_site_analytics(
    site_id: int,
    days: int = Query(default=30, ge=7, le=90),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    site = _resolve_admin_site(db, site_id)
    window = days if days in ALLOWED_DAYS else 30
    return collect_stats(db, site, days=window)
