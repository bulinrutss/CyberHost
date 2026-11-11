import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models.user import User
from app.models.vps import (
    OrderStatus,
    OrderType,
    PAYMENT_RECONCILE_STATUSES,
    VpsInstance,
    VpsOrder,
    VpsPlan,
    VpsStatus,
)
from app.schemas.vps import OrderCreate, OrderResponse
from app.services.abacatepay import (
    ORDER_KIND_VPS,
    AbacatePayService,
    apply_checkout_result,
    has_live_pix,
)
from app.services.hostname import assert_hostname_available
from app.services.coupons import redeem_coupon_for_order, release_coupon_reservation, reserve_coupon_for_order
from app.services import host_notify
from app.services.plan_presets import get_preset, list_plan_presets
from app.services.pricing import calculate_new_order_price, validate_plan_resources
from app.services.vmware.disk import normalize_disk_gb
from app.services.provision_progress import update_order_progress
from app.services.vmware.provisioner import VMwareProvisioner
from app.services.vps_renewal import apply_renewal_order
from app.services.vps_upgrade import apply_upgrade_order

router = APIRouter()
logger = logging.getLogger(__name__)


def _mark_order_failed(db: Session, order_id: int, message: str) -> None:
    db.rollback()
    order = db.get(VpsOrder, order_id)
    if not order:
        return
    if order.status in (OrderStatus.PROVISIONING, OrderStatus.PAID):
        order.status = OrderStatus.FAILED
        order.error_message = message[:2000]
        update_order_progress(db, order, progress=order.provision_progress or 0, step="failed")
        host_notify.on_provision_failed(
            db,
            kind="VPS",
            summary=order.hostname or f"pedido #{order.id}",
            customer_user_id=order.user_id,
            client_url="/dashboard/orders",
        )


def _is_mariadb_record_changed(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    return bool(args) and args[0] == 1020


def _try_claim_provisioning(db: Session, order_id: int) -> VpsOrder | None:
    """Reserva o pedido para um único worker (PAID → PROVISIONING)."""
    try:
        order = (
            db.query(VpsOrder)
            .filter(VpsOrder.id == order_id, VpsOrder.status == OrderStatus.PAID)
            .with_for_update()
            .first()
        )
        if not order:
            return None
        order.status = OrderStatus.PROVISIONING
        db.commit()
        db.refresh(order)
        return order
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            logger.debug("Concorrência ao reservar provisionamento do pedido %s", order_id)
            return None
        raise


def _enqueue_order_fulfillment(background_tasks: BackgroundTasks, order: VpsOrder) -> None:
    if order.order_type == OrderType.UPGRADE:
        background_tasks.add_task(_apply_upgrade_async, order.id)
    elif order.order_type == OrderType.RENEWAL:
        background_tasks.add_task(_apply_renewal_async, order.id)
    else:
        background_tasks.add_task(_provision_async, order.id)


def _mark_paid_and_enqueue(
    db: Session,
    order_id: int,
    background_tasks: BackgroundTasks,
) -> bool:
    """Marca pagamento confirmado uma única vez e enfileira provisionamento ou upgrade."""
    try:
        order = (
            db.query(VpsOrder)
            .filter(
                VpsOrder.id == order_id,
                VpsOrder.status.in_(PAYMENT_RECONCILE_STATUSES),
            )
            .with_for_update()
            .first()
        )
        if not order:
            return False

        order.status = OrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        db.commit()

        if order.coupon_id:
            redeem_coupon_for_order(db, order.id, order.coupon_id)
        _enqueue_order_fulfillment(background_tasks, order)
        _notify_vps_paid(db, order)
        return True
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            logger.debug("Concorrência ao marcar pedido %s como pago", order_id)
            return False
        raise


def _provision_async(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = _try_claim_provisioning(db, order_id)
        if not order:
            return
        if db.query(VpsInstance).filter(VpsInstance.order_id == order.id).first():
            return

        try:
            VMwareProvisioner().provision_order(db, order)
        except HTTPException as exc:
            message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            _mark_order_failed(db, order_id, message)
        except IntegrityError:
            db.rollback()
            if db.query(VpsInstance).filter(VpsInstance.order_id == order_id).first():
                return
            _mark_order_failed(db, order_id, "Conflito ao registrar a VPS (provisionamento duplicado).")
        except Exception as exc:
            _mark_order_failed(db, order_id, str(exc))
            logger.exception("Provisionamento falhou para pedido %s", order_id)
    finally:
        db.close()


def _apply_renewal_async(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = _try_claim_provisioning(db, order_id)
        if not order or order.order_type != OrderType.RENEWAL:
            return
        try:
            apply_renewal_order(db, order)
        except Exception as exc:
            _mark_order_failed(db, order_id, str(exc))
            logger.exception("Renovação falhou para pedido %s", order_id)
    finally:
        db.close()


def _apply_upgrade_async(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = _try_claim_provisioning(db, order_id)
        if not order or order.order_type != OrderType.UPGRADE:
            return
        try:
            apply_upgrade_order(db, order)
        except Exception as exc:
            _mark_order_failed(db, order_id, str(exc))
            logger.exception("Upgrade falhou para pedido %s", order_id)
    finally:
        db.close()


def _checkout_description(db: Session, order: VpsOrder) -> str:
    plan = db.get(VpsPlan, order.plan_id)
    plan_name = plan.name if plan else "VPS"

    if order.order_type == OrderType.RENEWAL:
        instance = db.get(VpsInstance, order.target_instance_id) if order.target_instance_id else None
        vm_name = instance.vm_name if instance else "servidor"
        return (
            f"Renovação {vm_name} — {order.renewal_months} mês(es) "
            f"({order.vcpu} vCPU / {order.ram_mb // 1024} GB RAM)"
        )

    if order.order_type == OrderType.UPGRADE:
        instance = db.get(VpsInstance, order.target_instance_id) if order.target_instance_id else None
        vm_name = instance.vm_name if instance else "servidor"
        return (
            f"Upgrade {vm_name} — {order.vcpu} vCPU / "
            f"{order.ram_mb // 1024} GB RAM / {order.disk_gb} GB disco"
        )

    return (
        f"{plan_name} {order.hostname} — {order.vcpu} vCPU / "
        f"{order.ram_mb // 1024} GB RAM / {order.disk_gb} GB NVMe"
    )


def _vps_kind_label(order: VpsOrder) -> str:
    if order.order_type == OrderType.RENEWAL:
        return "renovação VPS"
    if order.order_type == OrderType.UPGRADE:
        return "upgrade VPS"
    return "VPS"


def _notify_vps_paid(db: Session, order: VpsOrder) -> None:
    host_notify.on_payment_confirmed(
        db,
        kind=_vps_kind_label(order),
        summary=order.hostname or f"pedido #{order.id}",
        total_cents=order.total_cents or 0,
        customer_user_id=order.user_id,
        client_url="/dashboard/orders",
        admin_url="/admin?tab=vps",
    )


def _notify_vps_pending(db: Session, order: VpsOrder) -> None:
    host_notify.on_new_pending_order(
        db,
        kind=_vps_kind_label(order),
        summary=order.hostname or f"pedido #{order.id}",
        total_cents=order.total_cents or 0,
        customer_user_id=order.user_id,
        admin_url="/admin?tab=vps",
    )


def notify_vps_order_after_create(db: Session, order: VpsOrder) -> None:
    if order.status == OrderStatus.PENDING_PAYMENT:
        _notify_vps_pending(db, order)
    elif order.status == OrderStatus.PAID:
        _notify_vps_paid(db, order)

def _attach_checkout(
    db: Session,
    order: VpsOrder,
    user: User,
    description: str,
    background_tasks: BackgroundTasks | None,
    *,
    commit: bool = True,
    force_new: bool = False,
) -> None:
    pay = AbacatePayService()
    if (
        pay.payments_required
        and not force_new
        and has_live_pix(order)
        and order.status == OrderStatus.PENDING_PAYMENT
    ):
        return

    if order.total_cents <= 0:
        order.status = OrderStatus.PAID
        update_order_progress(db, order, progress=5, step="payment_confirmed")
        if commit:
            db.commit()
        if order.coupon_id:
            redeem_coupon_for_order(db, order.id, order.coupon_id)
        if background_tasks is not None:
            _enqueue_order_fulfillment(background_tasks, order)
        if commit:
            _notify_vps_paid(db, order)
        return

    checkout = pay.create_checkout(
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
        order.status = OrderStatus.PAID
        update_order_progress(db, order, progress=5, step="payment_confirmed")
        if commit:
            db.commit()
        if order.coupon_id:
            redeem_coupon_for_order(db, order.id, order.coupon_id)
        if background_tasks is not None:
            _enqueue_order_fulfillment(background_tasks, order)
        if commit:
            _notify_vps_paid(db, order)
    elif commit:
        db.commit()


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(
    payload: OrderCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    assert_hostname_available(db, payload.hostname)

    plan_presets = list_plan_presets(db, plan.id)
    subtotal = calculate_new_order_price(
        plan,
        payload.vcpu,
        payload.ram_mb,
        disk_gb,
        preset=preset,
        plan_presets=plan_presets,
    )
    discount, total, coupon = reserve_coupon_for_order(db, payload.coupon_code, subtotal)
    order = VpsOrder(
        user_id=user.id,
        plan_id=plan.id,
        vcpu=payload.vcpu,
        ram_mb=payload.ram_mb,
        disk_gb=disk_gb,
        os_template=payload.os_template,
        hostname=payload.hostname.lower(),
        order_type=OrderType.NEW,
        coupon_id=coupon.id if coupon else None,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=total,
        status=OrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    description = (
        f"{plan.name} {payload.hostname} — {payload.vcpu} vCPU / "
        f"{payload.ram_mb // 1024} GB RAM / {disk_gb} GB NVMe"
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


@router.get("", response_model=list[OrderResponse])
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(VpsOrder).filter(VpsOrder.user_id == user.id).order_by(VpsOrder.created_at.desc()).all()


@router.delete("/{order_id}", status_code=204)
def delete_pending_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(VpsOrder)
            .filter(
                VpsOrder.id == order_id,
                VpsOrder.user_id == user.id,
                VpsOrder.status == OrderStatus.PENDING_PAYMENT,
            )
            .with_for_update()
            .first()
        )
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            raise HTTPException(status_code=409, detail="Pedido em atualização, tente de novo") from exc
        raise
    if not order:
        existing = db.get(VpsOrder, order_id)
        if not existing or existing.user_id != user.id:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        raise HTTPException(
            status_code=400,
            detail="Somente pedidos aguardando pagamento podem ser cancelados",
        )
    release_coupon_reservation(db, order.id, order.coupon_id)
    order.status = OrderStatus.CANCELLED
    order.provision_step = "cancelled_by_user"
    db.commit()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(VpsOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.post("/{order_id}/retry-checkout", response_model=OrderResponse)
def retry_order_checkout(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gera checkout Abacate Pay para pedidos pendentes sem URL de pagamento."""
    order = db.get(VpsOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Pedido não está aguardando pagamento")

    pay = AbacatePayService()
    if not pay.payments_required:
        raise HTTPException(status_code=400, detail="Pagamento não está habilitado")

    try:
        _attach_checkout(
            db,
            order,
            user,
            _checkout_description(db, order),
            background_tasks,
            force_new=not has_live_pix(order),
        )
    except HTTPException:
        db.rollback()
        raise
    db.refresh(order)
    return order


@router.post("/{order_id}/sync-payment", response_model=OrderResponse)
def sync_order_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Consulta status na Abacate Pay quando o webhook não chega (ex.: localhost)."""
    order = db.get(VpsOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if order.status not in PAYMENT_RECONCILE_STATUSES:
        return order

    pay = AbacatePayService()
    if not pay.payments_required:
        return order

    if order.status == OrderStatus.PENDING_PAYMENT and not has_live_pix(order):
        try:
            _attach_checkout(
                db,
                order,
                user,
                _checkout_description(db, order),
                background_tasks,
                force_new=True,
            )
        except HTTPException:
            db.rollback()
            raise
        db.refresh(order)

    if order.payment_external_id and pay.order_is_paid_at_provider(order, ORDER_KIND_VPS):
        _mark_paid_and_enqueue(db, order.id, background_tasks)

    db.refresh(order)
    return order


@router.post("/{order_id}/confirm-payment", response_model=OrderResponse)
def confirm_payment_test(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Simula pagamento confirmado (somente com SKIP_PAYMENT_FOR_TESTING)."""
    if not AbacatePayService().payment_bypass_enabled:
        raise HTTPException(
            status_code=403,
            detail="Pagamento real ativo — pague o Pix na tela do pedido",
        )
    order = db.get(VpsOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID):
        raise HTTPException(status_code=400, detail=f"Pedido em status inválido: {order.status}")

    order.status = OrderStatus.PAID
    update_order_progress(db, order, progress=5, step="payment_confirmed")
    db.commit()
    _enqueue_order_fulfillment(background_tasks, order)
    db.refresh(order)
    return order
