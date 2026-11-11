import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models.user import User
from app.models.web_site import (
    PAYMENT_RECONCILE_STATUSES,
    WebOrder,
    WebOrderStatus,
    WebOrderType,
    WebSite,
)
from app.services.web_renewal import apply_web_renewal_order
from app.schemas.web_site import WebOrderCreate, WebOrderResponse
from app.services.abacatepay import (
    ORDER_KIND_WEB,
    AbacatePayService,
    apply_checkout_result,
    has_live_pix,
)
from app.services import host_notify
from app.services.web_domain import domain_in_use, normalize_domain
from app.services.web_slug import normalize_slug
from app.services.coupons import redeem_coupon_for_web_order, release_web_coupon_reservation, reserve_coupon_for_order
from app.services.web_plan_presets import get_preset
from app.services.web_provisioner import provision_order


def require_web_hosting() -> None:
    if not get_settings().web_hosting_enabled:
        raise HTTPException(status_code=404, detail="Hospedagem de sites indisponível")


router = APIRouter(dependencies=[Depends(require_web_hosting)])
logger = logging.getLogger(__name__)


def _mark_order_failed(db: Session, order_id: int, message: str) -> None:
    db.rollback()
    order = db.get(WebOrder, order_id)
    if not order:
        return
    if order.status in (WebOrderStatus.PROVISIONING, WebOrderStatus.PAID):
        order.status = WebOrderStatus.FAILED
        order.error_message = message[:2000]
        order.provision_step = "failed"
        db.commit()
        host_notify.on_provision_failed(
            db,
            kind="site",
            summary=order.domain or order.site_slug or f"pedido #{order.id}",
            customer_user_id=order.user_id,
            client_url="/dashboard/sites",
        )


def _is_mariadb_record_changed(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    return bool(args) and args[0] == 1020


def _try_claim_provisioning(db: Session, order_id: int) -> WebOrder | None:
    try:
        order = (
            db.query(WebOrder)
            .filter(WebOrder.id == order_id, WebOrder.status == WebOrderStatus.PAID)
            .with_for_update()
            .first()
        )
        if not order:
            return None
        order.status = WebOrderStatus.PROVISIONING
        db.commit()
        db.refresh(order)
        return order
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            return None
        raise


def _provision_async(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = db.get(WebOrder, order_id)
        if order and order.order_type == WebOrderType.RENEWAL:
            if order.status not in (WebOrderStatus.PAID, WebOrderStatus.PROVISIONING):
                return
            if order.status == WebOrderStatus.PAID:
                order.status = WebOrderStatus.PROVISIONING
                order.provision_step = "configuring"
                db.commit()
            try:
                apply_web_renewal_order(db, order)
            except Exception as exc:
                _mark_order_failed(db, order_id, str(exc))
                logger.exception("Renovação de site falhou pedido %s", order_id)
            return
        order = _try_claim_provisioning(db, order_id)
        if not order:
            return
        if db.query(WebSite).filter(WebSite.order_id == order.id).first():
            return
        try:
            site = provision_order(db, order)
            host_notify.on_provision_ready(
                db,
                kind="site",
                summary=site.domain,
                customer_user_id=order.user_id,
                client_url="/dashboard/sites",
            )
        except Exception as exc:
            _mark_order_failed(db, order_id, str(exc))
            logger.exception("Provisionamento de site falhou pedido %s", order_id)
    finally:
        db.close()


def mark_web_paid_and_enqueue(
    db: Session,
    order_id: int,
    background_tasks: BackgroundTasks,
) -> bool:
    try:
        order = (
            db.query(WebOrder)
            .filter(
                WebOrder.id == order_id,
                WebOrder.status.in_(PAYMENT_RECONCILE_STATUSES),
            )
            .with_for_update()
            .first()
        )
        if not order:
            return False
        order.status = WebOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        db.commit()
        is_renewal = order.order_type == WebOrderType.RENEWAL
        if order.coupon_id and not is_renewal:
            redeem_coupon_for_web_order(db, order.id, order.coupon_id)
        background_tasks.add_task(_provision_async, order.id)
        client_url = (
            f"/dashboard/sites/{order.target_site_id}"
            if is_renewal and order.target_site_id
            else "/dashboard/sites"
        )
        host_notify.on_payment_confirmed(
            db,
            kind="Renovação site" if is_renewal else "site",
            summary=order.domain or order.site_slug or f"pedido #{order.id}",
            total_cents=order.total_cents or 0,
            customer_user_id=order.user_id,
            client_url=client_url,
            admin_url="/admin?tab=accounts",
        )
        return True
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            return False
        raise


def _slug_taken(db: Session, slug: str, *, ignore_order_id: int | None = None) -> bool:
    site_q = db.query(WebSite).filter(WebSite.site_slug == slug)
    if site_q.first():
        return True
    order_q = db.query(WebOrder).filter(
        WebOrder.site_slug == slug,
        WebOrder.order_type == WebOrderType.NEW,
        WebOrder.status.in_(
            (
                WebOrderStatus.PENDING_PAYMENT,
                WebOrderStatus.PAID,
                WebOrderStatus.PROVISIONING,
                WebOrderStatus.ACTIVE,
            )
        ),
    )
    if ignore_order_id:
        order_q = order_q.filter(WebOrder.id != ignore_order_id)
    return order_q.first() is not None


def _finalize_paid_web_order(
    db: Session,
    order: WebOrder,
    background_tasks: BackgroundTasks | None,
) -> None:
    is_renewal = order.order_type == WebOrderType.RENEWAL
    if order.coupon_id and not is_renewal:
        redeem_coupon_for_web_order(db, order.id, order.coupon_id)
    if background_tasks is not None:
        background_tasks.add_task(_provision_async, order.id)


def _attach_checkout(
    db: Session,
    order: WebOrder,
    user: User,
    description: str,
    background_tasks: BackgroundTasks | None,
    *,
    commit: bool = True,
    force_new: bool = False,
) -> bool:
    """Retorna True se o pedido ficou pago e precisa provisionar após o commit."""
    pay = AbacatePayService()
    if (
        pay.payments_required
        and not force_new
        and has_live_pix(order)
        and order.status == WebOrderStatus.PENDING_PAYMENT
    ):
        return False

    if order.total_cents <= 0:
        order.status = WebOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        if commit:
            db.commit()
            _finalize_paid_web_order(db, order, background_tasks)
        return True

    checkout = pay.create_web_checkout(
        order_id=order.id,
        amount_cents=order.total_cents,
        customer_phone=user.phone,
        description=description,
    )
    apply_checkout_result(order, checkout)

    if pay.payments_required:
        if commit:
            db.commit()
    elif pay.payment_bypass_enabled:
        order.status = WebOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        if commit:
            db.commit()
            _finalize_paid_web_order(db, order, background_tasks)
        return True
    elif commit:
        db.commit()
    return False


@router.post("", response_model=WebOrderResponse, status_code=201)
def create_web_order(
    payload: WebOrderCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preset = get_preset(db, payload.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    slug = normalize_slug(payload.site_slug)
    if _slug_taken(db, slug):
        raise HTTPException(status_code=400, detail="Este nome de site já está em uso")
    domain: str | None = None
    domain_raw = (payload.domain or "").strip()
    if domain_raw:
        domain = normalize_domain(domain_raw)
        if domain_in_use(db, domain):
            raise HTTPException(status_code=400, detail="Este domínio já está em uso")
    subtotal = preset.price_cents
    discount, total, coupon = reserve_coupon_for_order(db, payload.coupon_code, subtotal)
    order = WebOrder(
        user_id=user.id,
        preset_id=preset.id,
        site_slug=slug,
        domain=domain,
        ram_mb=preset.ram_mb,
        disk_mb=preset.disk_mb,
        cpu_percent=preset.cpu_percent,
        php_enabled=preset.php_enabled,
        coupon_id=coupon.id if coupon else None,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=total,
        status=WebOrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    try:
        needs_provision = False
        with db.begin_nested():
            db.add(order)
            db.flush()
            needs_provision = _attach_checkout(
                db,
                order,
                user,
                f"Site {preset.name} — {domain or slug}",
                background_tasks,
                commit=False,
            )
        db.commit()
        db.refresh(order)
        if needs_provision:
            _finalize_paid_web_order(db, order, background_tasks)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Não foi possível criar o pedido") from exc
    db.refresh(order)
    return WebOrderResponse.from_order(order)


@router.get("", response_model=list[WebOrderResponse])
def list_web_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = (
        db.query(WebOrder)
        .filter(WebOrder.user_id == user.id)
        .order_by(WebOrder.created_at.desc())
        .all()
    )
    return [WebOrderResponse.from_order(item) for item in orders]


@router.delete("/{order_id}", status_code=204)
def delete_pending_web_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(WebOrder)
        .filter(
            WebOrder.id == order_id,
            WebOrder.user_id == user.id,
            WebOrder.status == WebOrderStatus.PENDING_PAYMENT,
        )
        .first()
    )
    if not order:
        existing = db.get(WebOrder, order_id)
        if not existing or existing.user_id != user.id:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        raise HTTPException(status_code=400, detail="Somente pedidos aguardando pagamento podem ser cancelados")
    release_web_coupon_reservation(db, order.id, order.coupon_id)
    order.status = WebOrderStatus.CANCELLED
    order.provision_step = "cancelled_by_user"
    db.commit()


@router.get("/{order_id}", response_model=WebOrderResponse)
def get_web_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(WebOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return WebOrderResponse.from_order(order)


@router.post("/{order_id}/retry-checkout", response_model=WebOrderResponse)
def retry_web_checkout(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(WebOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status != WebOrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Pedido não está aguardando pagamento")
    pay = AbacatePayService()
    if not pay.payments_required:
        raise HTTPException(status_code=400, detail="Pagamento não está habilitado")
    _attach_checkout(
        db,
        order,
        user,
        f"Site — {order.domain}",
        background_tasks,
        force_new=not has_live_pix(order),
    )
    db.refresh(order)
    return WebOrderResponse.from_order(order)


@router.post("/{order_id}/sync-payment", response_model=WebOrderResponse)
def sync_web_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(WebOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status not in PAYMENT_RECONCILE_STATUSES:
        return WebOrderResponse.from_order(order)
    pay = AbacatePayService()
    if pay.payments_required:
        if order.status == WebOrderStatus.PENDING_PAYMENT and not has_live_pix(order):
            _attach_checkout(
                db, order, user, f"Site — {order.domain}", background_tasks, force_new=True
            )
            db.refresh(order)
        if order.payment_external_id and pay.order_is_paid_at_provider(order, ORDER_KIND_WEB):
            mark_web_paid_and_enqueue(db, order.id, background_tasks)
    db.refresh(order)
    return WebOrderResponse.from_order(order)
