from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload

from app.api.orders import _attach_checkout, notify_vps_order_after_create
from app.auth import get_current_user
from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsPlan, VpsPlanPreset, VpsStatus
from app.schemas.vps import (
    BillingInfo,
    OrderResponse,
    OsTemplateResponse,
    PlanPresetResponse,
    PlanResponse,
    PriceQuoteRequest,
    PriceQuoteResponse,
    RenewQuoteRequest,
    RenewQuoteResponse,
    UpgradeQuoteRequest,
    UpgradeQuoteResponse,
    VpsActionResponse,
    VpsConsoleResponse,
    VpsConsoleTicketResponse,
    VpsConsoleWsTicketResponse,
    VpsConnectionDomainCreate,
    VpsConnectionDomainResponse,
    VpsInstanceDetailResponse,
    VpsInstanceListResponse,
    WindowsCredentials,
)
from app.services import vps_actions
from app.services.auth_step_up import require_step_up
from app.services.billing import (
    assert_billing_allows_destroy,
    calculate_monthly_cents,
    calculate_renewal_price,
    quote_renewal_price,
    extend_paid_until,
    get_billing_snapshot,
)
from app.services.coupons import apply_coupon_to_subtotal, normalize_coupon_code
from app.services.os_templates import list_os_templates, spec_warnings
from app.services.plan_presets import get_preset, list_plan_presets
from app.services.vmware.disk import normalize_disk_gb
from app.services.pricing import (
    calculate_flexible_price,
    calculate_new_order_price,
    calculate_upgrade_quote,
    classify_upgrade_direction,
    prorate_upgrade_amount,
    validate_plan_resources,
)

from app.services.vps_renewal import resolve_renewal_order_block
from app.services.vps_connection_domains import (
    connection_to_dict,
    list_for_instance,
    remove_connection_domain,
    upsert_connection_domain,
)
from app.services.vps_nginx import remove_snippet
from app.services.vmware.console import acquire_webmks_ticket
from app.services.console_tickets import authenticate_console_websocket, issue_console_ws_ticket

router = APIRouter()


@router.get("/os-templates", response_model=list[OsTemplateResponse])
def list_os_template_options():
    return [
        OsTemplateResponse(
            slug=t.slug,
            label=t.label,
            template_name=t.template_name,
            is_recommended=t.is_recommended,
            recommended_min_vcpu=t.recommended_min_vcpu,
            recommended_min_ram_mb=t.recommended_min_ram_mb,
            recommended_min_disk_gb=t.recommended_min_disk_gb,
            description=t.description,
        )
        for t in list_os_templates()
    ]


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    return (
        db.query(VpsPlan)
        .filter(VpsPlan.is_active.is_(True))
        .order_by(VpsPlan.id)
        .all()
    )


@router.get("/presets", response_model=list[PlanPresetResponse])
def list_presets(plan_slug: str | None = None, db: Session = Depends(get_db)):
    query = (
        db.query(VpsPlanPreset)
        .join(VpsPlan)
        .filter(VpsPlanPreset.is_active.is_(True), VpsPlan.is_active.is_(True))
    )
    if plan_slug:
        query = query.filter(VpsPlan.slug == plan_slug)
    return query.order_by(VpsPlan.id, VpsPlanPreset.sort_order).all()


@router.post("/quote", response_model=PriceQuoteResponse)
def price_quote(payload: PriceQuoteRequest, db: Session = Depends(get_db)):
    plan = db.get(VpsPlan, payload.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    preset = None
    if payload.preset_id:
        preset = get_preset(db, payload.preset_id, plan.id)
        if not preset:
            raise HTTPException(status_code=404, detail="Plano predefinido não encontrado")

    disk_gb = normalize_disk_gb(payload.disk_gb, plan_default=plan.default_disk_gb)
    validate_plan_resources(plan, payload.vcpu, payload.ram_mb, disk_gb)
    plan_presets = list_plan_presets(db, plan.id)
    subtotal = calculate_new_order_price(
        plan,
        payload.vcpu,
        payload.ram_mb,
        disk_gb,
        preset=preset,
        plan_presets=plan_presets,
    )
    discount, total, coupon = apply_coupon_to_subtotal(db, payload.coupon_code, subtotal)
    warnings = spec_warnings(
        payload.os_template,
        vcpu=payload.vcpu,
        ram_mb=payload.ram_mb,
        disk_gb=disk_gb,
    )
    return PriceQuoteResponse(
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=total,
        monthly_cents=total,
        coupon_code=normalize_coupon_code(coupon.code) if coupon else None,
        warnings=warnings,
        vcpu=payload.vcpu,
        ram_mb=payload.ram_mb,
        disk_gb=disk_gb,
        os_template=payload.os_template,
    )


def _resolve_instance_plan(db: Session, instance: VpsInstance) -> VpsPlan:
    if instance.plan_id:
        plan = db.get(VpsPlan, instance.plan_id)
        if plan and plan.is_active:
            return plan
    if instance.order and instance.order.plan_id:
        plan = db.get(VpsPlan, instance.order.plan_id)
        if plan and plan.is_active:
            return plan
    plan = db.query(VpsPlan).filter(VpsPlan.slug == "vps", VpsPlan.is_active.is_(True)).first()
    if not plan:
        raise HTTPException(status_code=500, detail="Plano padrão não configurado")
    return plan


def _assert_upgrade_allowed(instance: VpsInstance) -> None:
    if not instance.paid_until:
        raise HTTPException(
            status_code=400,
            detail="VPS sem vencimento configurado. Entre em contato com o suporte.",
        )
    if get_billing_snapshot(instance)["billing_state"] == "suspended":
        raise HTTPException(
            status_code=402,
            detail="Mensalidade vencida. Renove antes de fazer upgrade.",
        )


def _pending_order(
    db: Session,
    instance_id: int,
    order_type: OrderType,
) -> VpsOrder | None:
    return (
        db.query(VpsOrder)
        .filter(
            VpsOrder.target_instance_id == instance_id,
            VpsOrder.order_type == order_type,
            VpsOrder.status.in_(
                [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.PROVISIONING]
            ),
        )
        .first()
    )


def _resolve_upgrade_order_block(db: Session, instance_id: int) -> VpsOrder | None:
    """
    Upgrade em PAID/PROVISIONING bloqueia novo pedido.
    Upgrade abandonado (PENDING_PAYMENT) é cancelado para liberar novo checkout.
    """
    pending = _pending_order(db, instance_id, OrderType.UPGRADE)
    if not pending:
        return None
    if pending.status == OrderStatus.PENDING_PAYMENT:
        pending.status = OrderStatus.CANCELLED
        pending.provision_step = "cancelled_new_upgrade"
        db.commit()
        return None
    return pending


@router.post("/instances/{instance_id}/renew/quote", response_model=RenewQuoteResponse)
def renew_quote(
    instance_id: int,
    payload: RenewQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    if instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING, VpsStatus.DELETED):
        raise HTTPException(status_code=400, detail="Servidor ainda não está pronto para renovação")
    if not instance.paid_until:
        raise HTTPException(status_code=400, detail="VPS sem ciclo de cobrança configurado")

    plan = _resolve_instance_plan(db, instance)
    presets = list_plan_presets(db, plan.id)
    quote = quote_renewal_price(plan, instance, payload.months, plan_presets=presets, user=user)
    billing = BillingInfo(**get_billing_snapshot(instance, monthly_cents=quote["monthly_cents"]))
    new_paid_until = extend_paid_until(
        instance.paid_until, payload.months, instance.billing_day
    )
    return RenewQuoteResponse(
        months=quote["months"],
        monthly_cents=quote["monthly_cents"],
        subtotal_cents=quote["subtotal_cents"],
        discount_cents=quote["discount_cents"],
        discount_percent=quote["discount_percent"],
        total_cents=quote["total_cents"],
        paid_until=instance.paid_until,
        new_paid_until=new_paid_until,
        billing=billing,
    )


@router.post("/instances/{instance_id}/renew", response_model=OrderResponse, status_code=201)
def create_renewal_order(
    instance_id: int,
    payload: RenewQuoteRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    if instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING, VpsStatus.DELETED):
        raise HTTPException(status_code=400, detail="Servidor ainda não está pronto para renovação")
    if not instance.paid_until:
        raise HTTPException(status_code=400, detail="VPS sem ciclo de cobrança configurado")

    if resolve_renewal_order_block(db, instance.id):
        raise HTTPException(
            status_code=400,
            detail="Já existe uma renovação em andamento para este servidor",
        )

    plan = _resolve_instance_plan(db, instance)
    presets = list_plan_presets(db, plan.id)
    quote = quote_renewal_price(plan, instance, payload.months, plan_presets=presets, user=user)

    order = VpsOrder(
        user_id=user.id,
        plan_id=plan.id,
        vcpu=instance.vcpu,
        ram_mb=instance.ram_mb,
        disk_gb=instance.disk_gb,
        hostname=f"renew-{instance.id}",
        order_type=OrderType.RENEWAL,
        target_instance_id=instance.id,
        renewal_months=payload.months,
        subtotal_cents=quote["subtotal_cents"] + quote["pending_cents"],
        discount_cents=quote["discount_cents"],
        total_cents=quote["total_cents"],
        status=OrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    description = (
        f"Renovação {instance.vm_name} — {payload.months} mês(es) "
        f"({instance.vcpu} vCPU / {instance.ram_mb // 1024} GB RAM)"
    )
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
            db.refresh(order)
            _attach_checkout(db, order, user, description, background_tasks, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    db.refresh(order)
    notify_vps_order_after_create(db, order)
    return order


def _prepare_upgrade(db: Session, instance: VpsInstance, payload: UpgradeQuoteRequest) -> dict:
    current_plan = _resolve_instance_plan(db, instance)
    current_presets = list_plan_presets(db, current_plan.id)
    current_monthly = calculate_monthly_cents(
        current_plan, instance, plan_presets=current_presets
    )
    current_disk = instance.disk_gb or current_plan.default_disk_gb
    current_network = instance.network_mbps or current_plan.network_mbps

    if payload.preset_id is not None:
        preset = get_preset(db, payload.preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Plano predefinido não encontrado")
        target_plan = db.get(VpsPlan, preset.plan_id)
        if not target_plan or not target_plan.is_active:
            raise HTTPException(status_code=404, detail="Plano não encontrado")
        target_vcpu = preset.vcpu
        target_ram_mb = preset.ram_mb
        target_disk_gb = preset.disk_gb
        target_network = target_plan.network_mbps
        direction = classify_upgrade_direction(
            current_vcpu=instance.vcpu,
            current_ram_mb=instance.ram_mb,
            current_disk_gb=current_disk,
            current_network_mbps=current_network,
            target_vcpu=target_vcpu,
            target_ram_mb=target_ram_mb,
            target_disk_gb=target_disk_gb,
            target_network_mbps=target_network,
        )
        if direction != "upgrade":
            raise HTTPException(
                status_code=400,
                detail="Só é possível trocar para um plano maior (mais vCPU, RAM, disco ou rede).",
            )
        new_monthly = int(preset.price_cents)
        if new_monthly <= current_monthly:
            raise HTTPException(
                status_code=400,
                detail="Esse plano não aumenta a mensalidade.",
            )
        validate_plan_resources(target_plan, target_vcpu, target_ram_mb, target_disk_gb)
        quote = prorate_upgrade_amount(instance, new_monthly - current_monthly)
        return {
            "current_plan": current_plan,
            "target_plan": target_plan,
            "target_vcpu": target_vcpu,
            "target_ram_mb": target_ram_mb,
            "target_disk_gb": target_disk_gb,
            "current_disk": current_disk,
            "quote": quote,
            "current_monthly_cents": current_monthly,
            "new_monthly_cents": new_monthly,
        }

    validate_plan_resources(
        current_plan, payload.target_vcpu, payload.target_ram_mb, payload.target_disk_gb
    )
    quote = calculate_upgrade_quote(
        current_plan,
        instance,
        payload.target_vcpu,
        payload.target_ram_mb,
        payload.target_disk_gb,
        plan_presets=current_presets,
    )
    return {
        "current_plan": current_plan,
        "target_plan": current_plan,
        "target_vcpu": payload.target_vcpu,
        "target_ram_mb": payload.target_ram_mb,
        "target_disk_gb": payload.target_disk_gb,
        "current_disk": current_disk,
        "quote": quote,
        "current_monthly_cents": current_monthly,
        "new_monthly_cents": current_monthly + quote["monthly_delta_cents"],
    }


def _upgrade_quote_response(instance: VpsInstance, prepared: dict) -> UpgradeQuoteResponse:
    quote = prepared["quote"]
    return UpgradeQuoteResponse(
        current_vcpu=instance.vcpu,
        current_ram_mb=instance.ram_mb,
        current_disk_gb=prepared["current_disk"],
        target_vcpu=prepared["target_vcpu"],
        target_ram_mb=prepared["target_ram_mb"],
        target_disk_gb=prepared["target_disk_gb"],
        total_cents=quote["total_cents"],
        monthly_delta_cents=quote["monthly_delta_cents"],
        current_monthly_cents=prepared["current_monthly_cents"],
        new_monthly_cents=prepared["new_monthly_cents"],
        days_remaining=quote["days_remaining"],
        period_days=quote["period_days"],
        prorated=quote["prorated"],
        paid_until=instance.paid_until,
        plan=prepared["target_plan"],
    )


@router.post("/instances/{instance_id}/upgrade/quote", response_model=UpgradeQuoteResponse)
def upgrade_quote(
    instance_id: int,
    payload: UpgradeQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    if instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING, VpsStatus.DELETED):
        raise HTTPException(status_code=400, detail="Servidor ainda não está pronto para upgrade")
    _assert_upgrade_allowed(instance)
    prepared = _prepare_upgrade(db, instance, payload)
    return _upgrade_quote_response(instance, prepared)


@router.post("/instances/{instance_id}/upgrade", response_model=OrderResponse, status_code=201)
def create_upgrade_order(
    instance_id: int,
    payload: UpgradeQuoteRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    if instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING, VpsStatus.DELETED):
        raise HTTPException(status_code=400, detail="Servidor ainda não está pronto para upgrade")
    _assert_upgrade_allowed(instance)

    blocking = _resolve_upgrade_order_block(db, instance.id)
    if blocking:
        raise HTTPException(
            status_code=400,
            detail="Já existe um upgrade em andamento para este servidor",
        )

    prepared = _prepare_upgrade(db, instance, payload)
    target_plan = prepared["target_plan"]
    quote = prepared["quote"]
    total = quote["total_cents"]

    order = VpsOrder(
        user_id=user.id,
        plan_id=target_plan.id,
        vcpu=prepared["target_vcpu"],
        ram_mb=prepared["target_ram_mb"],
        disk_gb=prepared["target_disk_gb"],
        hostname=f"upgrade-{instance.id}",
        order_type=OrderType.UPGRADE,
        target_instance_id=instance.id,
        total_cents=total,
        upgrade_monthly_delta_cents=quote["monthly_delta_cents"],
        status=OrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    description = (
        f"Upgrade {instance.vm_name} — {target_plan.name} · {prepared['target_vcpu']} vCPU / "
        f"{prepared['target_ram_mb'] // 1024} GB RAM / {prepared['target_disk_gb']} GB disco"
    )
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
            db.refresh(order)
            _attach_checkout(db, order, user, description, background_tasks, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    db.refresh(order)
    notify_vps_order_after_create(db, order)
    return order


@router.get("/instances", response_model=list[VpsInstanceListResponse])
def list_instances(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    instances = (
        db.query(VpsInstance)
        .options(
            joinedload(VpsInstance.order).joinedload(VpsOrder.plan),
            joinedload(VpsInstance.plan),
        )
        .filter(VpsInstance.user_id == user.id)
        .order_by(VpsInstance.created_at.desc())
        .all()
    )
    return vps_actions.build_instances_list(instances)


@router.get("/instances/{instance_id}", response_model=VpsInstanceDetailResponse)
async def get_instance(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import asyncio

    instance = vps_actions.resolve_instance(db, instance_id, user)
    vps_actions.heal_non_critical_guest_error(db, instance)
    plan = _resolve_instance_plan(db, instance)
    presets = list_plan_presets(db, plan.id) if plan else []

    def _build() -> dict:
        return vps_actions.build_instance_detail(
            instance, plan_presets=presets, db=db, include_secrets=False
        )

    return await asyncio.to_thread(_build)


@router.get(
    "/instances/{instance_id}/credentials",
    response_model=WindowsCredentials,
)
def get_instance_credentials(
    instance_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    creds = vps_actions.get_windows_credentials(instance, include_secrets=True)
    if not creds or not creds.get("password"):
        raise HTTPException(status_code=404, detail="Credenciais não disponíveis")
    return creds


def _action_response(instance: VpsInstance, message: str) -> VpsActionResponse:
    return VpsActionResponse(success=True, message=message, instance=instance)


@router.post("/instances/{instance_id}/power-on", response_model=VpsActionResponse)
def instance_power_on(
    instance_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    message = vps_actions.power_on_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/power-off", response_model=VpsActionResponse)
def instance_power_off(
    instance_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    message = vps_actions.power_off_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/reset", response_model=VpsActionResponse)
def instance_reset(
    instance_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    message = vps_actions.reset_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.delete("/instances/{instance_id}", response_model=VpsActionResponse)
def instance_destroy(
    instance_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    assert_billing_allows_destroy(instance)
    for conn in list_for_instance(db, instance):
        remove_snippet(conn)
    message = vps_actions.destroy_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.get(
    "/instances/{instance_id}/connections",
    response_model=list[VpsConnectionDomainResponse],
)
def list_connection_domains(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    return [connection_to_dict(c) for c in list_for_instance(db, instance)]


@router.put(
    "/instances/{instance_id}/connections",
    response_model=VpsConnectionDomainResponse,
)
def set_connection_domain(
    instance_id: int,
    payload: VpsConnectionDomainCreate,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    if instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING, VpsStatus.DELETED):
        raise HTTPException(status_code=400, detail="Servidor ainda não está pronto")
    conn = upsert_connection_domain(
        db,
        instance,
        user,
        domain_raw=payload.domain,
        public_port=payload.public_port,
    )
    return connection_to_dict(conn)


@router.delete("/instances/{instance_id}/connections/{connection_id}", status_code=204)
def delete_connection_domain(
    instance_id: int,
    connection_id: int,
    user: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    remove_connection_domain(db, instance, connection_id)


@router.get("/instances/{instance_id}/console", response_model=VpsConsoleResponse)
def instance_console_info(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    live = vps_actions.get_instance_live_status(instance)
    power_state = live["power_state"]
    provisioning = instance.status in (VpsStatus.CREATING, VpsStatus.CONFIGURING)
    available = power_state == "poweredOn" and not provisioning
    message = None
    if provisioning:
        message = "Console disponível quando o servidor terminar de ser criado."
    elif power_state != "poweredOn":
        message = "Ligue o servidor na aba Uso, controle & zona para abrir o console."
    return VpsConsoleResponse(
        available=available,
        power_state=power_state,
        ws_path=f"/api/vps/instances/{instance_id}/console/ws",
        message=message,
    )


@router.post("/instances/{instance_id}/console/ticket", response_model=VpsConsoleTicketResponse)
def instance_console_ticket(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    host, port, _ticket, wss_url = acquire_webmks_ticket(instance)
    return VpsConsoleTicketResponse(wss_url=wss_url, host=host, port=port)


@router.post("/instances/{instance_id}/console/ws-ticket", response_model=VpsConsoleWsTicketResponse)
def instance_console_ws_ticket(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, user)
    raw, ttl = issue_console_ws_ticket(db, user, instance.id)
    return VpsConsoleWsTicketResponse(
        ticket=raw,
        expires_in_seconds=ttl,
        ws_path=f"/api/vps/instances/{instance.id}/console/ws",
    )


@router.websocket("/instances/{instance_id}/console/ws")
async def instance_console_ws(
    websocket: WebSocket,
    instance_id: int,
    ticket: str | None = None,
    token: str | None = None,
):
    import asyncio
    import logging

    import websockets
    from websockets.exceptions import ConnectionClosed

    from app.config import get_settings
    from app.console_io import safe_print
    from app.esxi_tls import build_esxi_ssl_context

    logger = logging.getLogger(__name__)

    async def reject(message: str, *, code: int = 1011) -> None:
        await websocket.accept()
        await websocket.close(code=code, reason=message[:120])

    if token:
        await reject("Não autorizado", code=4401)
        return
    if not ticket:
        await reject("Ticket ausente", code=4401)
        return

    db = SessionLocal()
    try:
        user = authenticate_console_websocket(
            db, instance_id=instance_id, ticket=ticket, jwt_query=token
        )
        instance = vps_actions.resolve_instance(db, instance_id, user, admin=user.is_admin)
    except HTTPException as exc:
        logger.warning("Console WS auth falhou inst=%s: %s", instance_id, exc.detail)
        await reject("Não autorizado", code=4401)
        return
    except Exception:
        logger.exception("Console WS erro de sessão inst=%s", instance_id)
        await reject("Erro ao validar sessão")
        return
    finally:
        db.close()

    try:
        _host, _port, _ticket, esxi_url = await asyncio.to_thread(
            acquire_webmks_ticket, instance
        )
    except HTTPException as exc:
        await reject(str(exc.detail), code=4400)
        return
    except Exception:
        logger.exception("Console WS ticket falhou inst=%s", instance_id)
        await reject("Erro ao obter console")
        return

    settings = get_settings()
    ssl_ctx = build_esxi_ssl_context(settings)

    safe_print(f"[Console] INFO Conectando ESXi inst={instance_id} host={_host}:{_port}")

    # WMKS.js negocia "binary" como subprotocolo WebSocket.
    # ESXi rejeita a conexão se o subprotocolo não for "binary" ou "vmware-vvc".
    esxi_ws = None
    try:
        esxi_ws = await websockets.connect(
            esxi_url,
            ssl=ssl_ctx,
            subprotocols=["binary"],
            max_size=None,
            open_timeout=20,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=5,
        )
    except Exception as exc:
        logger.exception("Console WS ESXi falhou inst=%s url=%s", instance_id, esxi_url[:80])
        safe_print(f"[Console] ERRO ESXi inst={instance_id}: {exc}")
        await reject("Falha ao conectar o console")
        return

    await websocket.accept(subprotocol="binary")
    safe_print(f"[Console] INFO Proxy ativo inst={instance_id}")

    closed = asyncio.Event()

    async def client_to_esxi() -> None:
        try:
            while not closed.is_set():
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    closed.set()
                    break
                data = message.get("bytes")
                if data is None and message.get("text") is not None:
                    data = message["text"]
                if data is not None and esxi_ws is not None:
                    await esxi_ws.send(data)
        except WebSocketDisconnect:
            closed.set()
        except Exception:
            logger.exception("Console WS client->ESXi inst=%s", instance_id)
            closed.set()

    async def esxi_to_client() -> None:
        try:
            assert esxi_ws is not None
            async for data in esxi_ws:
                if closed.is_set():
                    break
                if isinstance(data, bytes):
                    await websocket.send_bytes(data)
                else:
                    await websocket.send_text(data)
        except ConnectionClosed:
            closed.set()
        except Exception:
            logger.exception("Console WS ESXi->client inst=%s", instance_id)
            closed.set()

    try:
        await asyncio.gather(client_to_esxi(), esxi_to_client())
    except WebSocketDisconnect:
        pass
    finally:
        closed.set()
        if esxi_ws is not None:
            await esxi_ws.close()
        safe_print(f"[Console] INFO Proxy encerrado inst={instance_id}")
