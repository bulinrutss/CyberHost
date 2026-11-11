from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.web_site import WebOrderStatus, WebSite, WebSiteStatus
from app.schemas.web_site import (
    WebBillingInfo,
    WebDomainUpdate,
    WebFileContent,
    WebFileEntry,
    WebFileMkdir,
    WebFileWrite,
    WebHostingDnsResponse,
    WebLogsResponse,
    WebPresetResponse,
    WebQuoteRequest,
    WebQuoteResponse,
    WebRenewQuoteRequest,
    WebRenewQuoteResponse,
    WebSiteDetail,
    WebSiteResponse,
)
from app.schemas.web_site import WebOrderResponse
from app.models.web_site import WebOrder, WebOrderStatus, WebOrderType
from app.api import web_orders as web_orders_api
from app.services.web_renewal import (
    quote_site_renewal,
    resolve_web_monthly_cents,
    resolve_web_renewal_order_block,
    get_web_billing_snapshot_for_site,
)
from app.schemas.web_page import WebPageConfig, WebPageEditorResponse
from app.schemas.web_site_analytics import WebSiteAnalyticsResponse
from app.services.auth_step_up import require_step_up
from app.services.web_page_builder import editor_state, save_avatar, save_page
from app.services.web_site_analytics import (
    ALLOWED_DAYS,
    collect_stats,
    record_page_view,
    resolve_click_redirect,
)
from app.services.web_domain import domain_in_use, normalize_domain
from app.services.web_slug import dns_target_host, normalize_slug, path_prefix, site_public_url
from app.services.web_files import (
    create_directory,
    delete_path,
    list_directory,
    read_file,
    tree_used_bytes,
    upload_file,
    write_file,
)
from app.services.coupons import apply_coupon_to_subtotal, normalize_coupon_code
from app.services.web_plan_presets import get_preset, list_presets
from app.services import web_nginx
from app.services import web_process
from app.services import web_ssl


def require_web_hosting() -> None:
    if not get_settings().web_hosting_enabled:
        raise HTTPException(status_code=404, detail="Hospedagem de sites indisponível")


router = APIRouter(dependencies=[Depends(require_web_hosting)])


def _resolve(db: Session, site_id: int, user: User) -> WebSite:
    site = (
        db.query(WebSite)
        .options(joinedload(WebSite.order))
        .filter(WebSite.id == site_id, WebSite.user_id == user.id)
        .first()
    )
    if not site or site.status == WebSiteStatus.DELETED:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return site


def _to_response(site: WebSite, db: Session, *, used: int | None = None) -> WebSiteDetail:
    order = site.order
    is_provisioning = bool(
        order and order.status in (WebOrderStatus.PAID, WebOrderStatus.PROVISIONING)
    )
    status = site.status.value if hasattr(site.status, "value") else str(site.status)
    billing = None
    if site.paid_until:
        monthly = resolve_web_monthly_cents(db, site)
        billing = get_web_billing_snapshot_for_site(db, site, monthly_cents=monthly)
    return WebSiteDetail(
        id=site.id,
        site_slug=site.site_slug,
        domain=site.domain,
        path_url=path_prefix(site.site_slug),
        ram_mb=site.ram_mb,
        disk_mb=site.disk_mb,
        cpu_percent=site.cpu_percent,
        php_enabled=site.php_enabled,
        port=site.port,
        status=status,
        is_provisioning=is_provisioning,
        error_message=site.error_message,
        public_url=site_public_url(site),
        dns_target=dns_target_host(),
        ssl_active=web_ssl.ssl_active_for_site(site),
        billing=billing,
        created_at=site.created_at,
        data_used_bytes=used if used is not None else 0,
        provision_progress=order.provision_progress if order else None,
        provision_label=order.provision_step if order else None,
    )


def build_site_detail(db: Session, site: WebSite, *, used: int | None = None) -> WebSiteDetail:
    return _to_response(site, db, used=used)


@router.get("/presets", response_model=list[WebPresetResponse])
def web_presets(db: Session = Depends(get_db)):
    return list_presets(db)


@router.get("/hosting-dns", response_model=WebHostingDnsResponse)
def web_hosting_dns():
    return WebHostingDnsResponse(dns_target=dns_target_host())


@router.post("/quote", response_model=WebQuoteResponse)
def web_quote(payload: WebQuoteRequest, db: Session = Depends(get_db)):
    preset = get_preset(db, payload.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    subtotal = preset.price_cents
    discount, total, coupon = apply_coupon_to_subtotal(db, payload.coupon_code, subtotal)
    return WebQuoteResponse(
        preset_id=preset.id,
        ram_mb=preset.ram_mb,
        disk_mb=preset.disk_mb,
        cpu_percent=preset.cpu_percent,
        php_enabled=preset.php_enabled,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=total,
        monthly_cents=total,
        coupon_code=normalize_coupon_code(coupon.code) if coupon else None,
    )


@router.get("/instances", response_model=list[WebSiteResponse])
def list_sites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sites = (
        db.query(WebSite)
        .options(joinedload(WebSite.order))
        .filter(WebSite.user_id == user.id, WebSite.status != WebSiteStatus.DELETED)
        .order_by(WebSite.created_at.desc())
        .all()
    )
    return [_to_response(site, db) for site in sites]


@router.get("/instances/{site_id}", response_model=WebSiteDetail)
def get_site(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _resolve(db, site_id, user)
    web_process.sync_site_status(site)
    db.commit()
    return _to_response(site, db, used=tree_used_bytes(site))


@router.post("/instances/{site_id}/renew/quote", response_model=WebRenewQuoteResponse)
def renew_site_quote(
    site_id: int,
    payload: WebRenewQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    if site.status in (WebSiteStatus.CREATING, WebSiteStatus.DELETED):
        raise HTTPException(status_code=400, detail="Site ainda não está pronto para renovação")
    if not site.paid_until:
        raise HTTPException(status_code=400, detail="Site sem ciclo de cobrança configurado")
    quote = quote_site_renewal(db, site, payload.months)
    return WebRenewQuoteResponse(
        months=quote["months"],
        monthly_cents=quote["monthly_cents"],
        subtotal_cents=quote["subtotal_cents"],
        discount_cents=quote["discount_cents"],
        discount_percent=quote["discount_percent"],
        total_cents=quote["total_cents"],
        paid_until=quote["paid_until"],
        new_paid_until=quote["new_paid_until"],
        billing=WebBillingInfo(**quote["billing"]),
    )


@router.post("/instances/{site_id}/renew", response_model=WebOrderResponse, status_code=201)
def create_site_renewal_order(
    site_id: int,
    payload: WebRenewQuoteRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    if site.status in (WebSiteStatus.CREATING, WebSiteStatus.DELETED):
        raise HTTPException(status_code=400, detail="Site ainda não está pronto para renovação")
    if not site.paid_until:
        raise HTTPException(status_code=400, detail="Site sem ciclo de cobrança configurado")
    if resolve_web_renewal_order_block(db, site.id):
        raise HTTPException(
            status_code=400,
            detail="Já existe uma renovação em andamento para este site",
        )

    quote = quote_site_renewal(db, site, payload.months)
    label = site.domain or site.site_slug
    order = WebOrder(
        user_id=user.id,
        order_type=WebOrderType.RENEWAL,
        target_site_id=site.id,
        renewal_months=payload.months,
        preset_id=site.order.preset_id if site.order else None,
        site_slug=site.site_slug,
        domain=site.domain,
        ram_mb=site.ram_mb,
        disk_mb=site.disk_mb,
        cpu_percent=site.cpu_percent,
        php_enabled=site.php_enabled,
        subtotal_cents=quote["subtotal_cents"],
        discount_cents=quote["discount_cents"],
        total_cents=quote["total_cents"],
        status=WebOrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    description = f"Renovação site {label} — {payload.months} mês(es)"
    try:
        needs_apply = False
        with db.begin_nested():
            db.add(order)
            db.flush()
            db.refresh(order)
            needs_apply = web_orders_api._attach_checkout(
                db,
                order,
                user,
                description,
                background_tasks,
                commit=False,
            )
        db.commit()
        db.refresh(order)
        if needs_apply:
            web_orders_api._finalize_paid_web_order(db, order, background_tasks)
    except HTTPException:
        db.rollback()
        raise
    return WebOrderResponse.from_order(order)


@router.post("/instances/{site_id}/start", response_model=WebSiteResponse)
def start_site(site_id: int, user: User = Depends(require_step_up), db: Session = Depends(get_db)):
    site = _resolve(db, site_id, user)
    try:
        web_process.start_site(site)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    return _to_response(site, db)


@router.post("/instances/{site_id}/stop", response_model=WebSiteResponse)
def stop_site(site_id: int, user: User = Depends(require_step_up), db: Session = Depends(get_db)):
    site = _resolve(db, site_id, user)
    web_process.stop_site(site)
    db.commit()
    return _to_response(site, db)


@router.post("/instances/{site_id}/restart", response_model=WebSiteResponse)
def restart_site(site_id: int, user: User = Depends(require_step_up), db: Session = Depends(get_db)):
    site = _resolve(db, site_id, user)
    web_process.stop_site(site)
    try:
        web_process.start_site(site)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    return _to_response(site, db)


@router.put("/instances/{site_id}/domain", response_model=WebSiteResponse)
def update_domain(
    site_id: int,
    payload: WebDomainUpdate,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
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
    return _to_response(site, db)


@router.post("/instances/{site_id}/ssl/refresh", response_model=WebSiteResponse)
def refresh_site_ssl(
    site_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    if not (site.domain or "").strip():
        raise HTTPException(status_code=400, detail="Configure um domínio antes de emitir SSL")
    try:
        ssl_ok, ssl_err = web_ssl.configure_domain_with_status(site, db=db)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    db.commit()
    if not ssl_ok:
        raise HTTPException(
            status_code=400,
            detail=ssl_err
            or "Não foi possível emitir o certificado SSL. "
            "Confira o DNS e, no Cloudflare, use Somente DNS (nuvem cinza) e tente de novo.",
        )
    return _to_response(site, db)


@router.get("/instances/{site_id}/page", response_model=WebPageEditorResponse)
def get_site_page_editor(
    site_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return editor_state(site)


@router.put("/instances/{site_id}/page", response_model=WebPageEditorResponse)
def save_site_page_editor(
    site_id: int,
    payload: WebPageConfig,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    save_page(site, payload)
    db.commit()
    return editor_state(site)


@router.post("/instances/{site_id}/page/avatar", response_model=WebPageEditorResponse)
def upload_site_page_avatar(
    site_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    save_avatar(site, file)
    db.commit()
    return editor_state(site)


@router.get("/instances/{site_id}/logs", response_model=WebLogsResponse)
def site_logs(
    site_id: int,
    tail: int = Query(default=100, ge=10, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return WebLogsResponse(lines=web_process.tail_logs(site.data_path, tail), tail=tail)


@router.get("/instances/{site_id}/files")
def site_files(
    site_id: int,
    path: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return list_directory(site, path)


@router.get("/instances/{site_id}/files/content", response_model=WebFileContent)
def site_file_content(
    site_id: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return read_file(site, path)


@router.put("/instances/{site_id}/files/content")
def site_file_write(
    site_id: int,
    payload: WebFileWrite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    write_file(site, payload.path, payload.content)
    return {"ok": True}


@router.post("/instances/{site_id}/files/mkdir", response_model=WebFileEntry)
def site_file_mkdir(
    site_id: int,
    payload: WebFileMkdir,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return create_directory(site, payload.path, payload.name)


@router.post("/instances/{site_id}/files/upload")
def site_file_upload(
    site_id: int,
    path: str = Query(default=""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    return upload_file(site, path, file)


@router.delete("/instances/{site_id}/files")
def site_file_delete(
    site_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    delete_path(site, path)
    return {"ok": True}


@router.get("/public/pv/{site_slug}")
def public_page_view(
    site_slug: str,
    request: Request,
    v: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
):
    record_page_view(db, request, site_slug=site_slug, visitor_id=v)
    db.commit()
    return Response(status_code=204)


@router.get("/r/{site_slug}/{link_id}")
def public_link_redirect(
    site_slug: str,
    link_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    target = resolve_click_redirect(db, request, site_slug=site_slug, link_id=link_id)
    return RedirectResponse(url=target, status_code=302)


@router.get("/instances/{site_id}/analytics", response_model=WebSiteAnalyticsResponse)
def site_analytics(
    site_id: int,
    days: int = Query(default=30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    site = _resolve(db, site_id, user)
    window = days if days in ALLOWED_DAYS else 30
    return collect_stats(db, site, days=window)
