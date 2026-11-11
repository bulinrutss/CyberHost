"""Compra e renovação mensal de espaço extra no CyberCloud."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query, Session

from app.models.cloud_storage_order import (
    CloudStorageOrder,
    CloudStorageOrderStatus,
    PAYMENT_RECONCILE_STATUSES,
)
from app.models.user import User
from app.services.abacatepay import (
    ORDER_KIND_CLOUD,
    AbacatePayService,
    apply_checkout_result,
    has_live_pix,
)
from app.services.billing import (
    calculate_cloud_renewal_price,
    extend_paid_until,
    get_cloud_billing_snapshot,
    initial_paid_until,
    user_cloud_billing_anchor,
)
from app.services.cloud_quota import GB, parse_storage_packages
from app.services import host_notify

GB_BYTES = GB


def _cloud_summary(order: CloudStorageOrder) -> str:
    if order.renewal_months and order.renewal_months >= 1:
        return f"Renovação CyberCloud — {order.renewal_months} mês(es)"
    if order.extra_gb:
        return f"CyberCloud +{order.extra_gb} GB"
    return f"CyberCloud pedido #{order.id}"


def _notify_cloud_pending(db: Session, order: CloudStorageOrder) -> None:
    host_notify.on_new_pending_order(
        db,
        kind="CyberCloud",
        summary=_cloud_summary(order),
        total_cents=order.total_cents or 0,
        customer_user_id=order.user_id,
        admin_url="/admin?tab=accounts",
    )


def _notify_cloud_paid(db: Session, order: CloudStorageOrder) -> None:
    host_notify.on_payment_confirmed(
        db,
        kind="CyberCloud",
        summary=_cloud_summary(order),
        total_cents=order.total_cents or 0,
        customer_user_id=order.user_id,
        client_url="/dashboard/files",
        admin_url="/admin?tab=accounts",
    )


def _for_update(query: Query, db: Session) -> Query:
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        return query.with_for_update()
    return query


def _is_mariadb_record_changed(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    return bool(args) and args[0] == 1020


def list_packages() -> list[dict]:
    return parse_storage_packages()


def _find_package(slug: str) -> dict | None:
    for pkg in parse_storage_packages():
        if pkg["slug"] == slug:
            return pkg
    return None


def monthly_cents_for_gb(extra_gb: int) -> int:
    packages = parse_storage_packages()
    if not packages:
        raise HTTPException(status_code=400, detail="Nenhum pacote de armazenamento configurado")
    pkg = next((p for p in packages if p["gb"] == extra_gb), None)
    if pkg:
        return pkg["price_cents"]
    ref = packages[0]
    return int(round(ref["price_cents"] / ref["gb"] * extra_gb))


def _ensure_cloud_billing_anchor(db: Session, user: User) -> None:
    if user.cloud_paid_until:
        return
    anchor_until, anchor_day = user_cloud_billing_anchor(db, user.id)
    if anchor_until:
        user.cloud_paid_until = anchor_until
        user.cloud_billing_day = anchor_day
    else:
        paid_until, billing_day = initial_paid_until()
        user.cloud_paid_until = paid_until
        user.cloud_billing_day = billing_day


def apply_subscription_gb(
    db: Session,
    user: User,
    extra_gb: int,
    *,
    increase_monthly: bool = True,
) -> None:
    if extra_gb <= 0:
        raise HTTPException(status_code=400, detail="Informe GB positivo")
    _ensure_cloud_billing_anchor(db, user)
    user.cloud_contracted_gb = int(user.cloud_contracted_gb or 0) + extra_gb
    if increase_monthly:
        user.cloud_monthly_cents = int(user.cloud_monthly_cents or 0) + monthly_cents_for_gb(extra_gb)
    user.cloud_suspended_for_billing = False
    db.flush()
    db.refresh(user)


def quote_purchase(db: Session, user: User, package_slug: str) -> dict:
    """Preço do pacote com prorrata até o vencimento da assinatura ou VPS do cliente."""
    from app.services.billing import prorate_monthly_delta

    pkg = _find_package(package_slug.strip().lower())
    if not pkg:
        raise HTTPException(status_code=404, detail="Pacote de armazenamento não encontrado")

    if user.cloud_paid_until:
        paid_until = user.cloud_paid_until
        billing_day = user.cloud_billing_day or paid_until.day
    else:
        paid_until, billing_day = user_cloud_billing_anchor(db, user.id)

    proration = prorate_monthly_delta(pkg["price_cents"], paid_until, billing_day)
    return {
        "slug": pkg["slug"],
        "gb": pkg["gb"],
        "list_price_cents": pkg["price_cents"],
        "total_cents": proration["amount_cents"],
        "monthly_price_cents": pkg["price_cents"],
        "paid_until": paid_until.isoformat() if paid_until else None,
        **proration,
    }


def create_purchase(db: Session, user: User, package_slug: str) -> CloudStorageOrder:
    pkg = _find_package(package_slug.strip().lower())
    if not pkg:
        raise HTTPException(status_code=404, detail="Pacote de armazenamento não encontrado")

    quote = quote_purchase(db, user, package_slug)
    charge_cents = quote["total_cents"]

    order = CloudStorageOrder(
        user_id=user.id,
        extra_gb=pkg["gb"],
        total_cents=charge_cents,
        status=CloudStorageOrderStatus.PENDING_PAYMENT,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    pay = AbacatePayService()
    checkout = pay.create_storage_checkout(
        order_id=order.id,
        amount_cents=order.total_cents,
        customer_phone=user.phone,
        description=f"+{order.extra_gb} GB CyberCloud/mês",
    )
    apply_checkout_result(order, checkout)

    if not pay.payments_required:
        mark_paid(db, order.id)

    db.commit()
    db.refresh(order)
    if order.status == CloudStorageOrderStatus.PENDING_PAYMENT:
        _notify_cloud_pending(db, order)
    return order


def quote_renewal(db: Session, user: User, months: int) -> dict:
    if not user.cloud_paid_until:
        raise HTTPException(status_code=400, detail="Assinatura CyberCloud sem vencimento configurado")
    total = calculate_cloud_renewal_price(user, months)
    new_paid_until = extend_paid_until(
        user.cloud_paid_until,
        months,
        user.cloud_billing_day or user.cloud_paid_until.day,
    )
    billing = get_cloud_billing_snapshot(user)
    return {
        "months": months,
        "monthly_cents": int(user.cloud_monthly_cents or 0),
        "total_cents": total,
        "pending_cents": int(user.admin_pending_cloud_charge_cents or 0),
        "new_paid_until": new_paid_until,
        "contracted_gb": int(user.cloud_contracted_gb or 0),
        "billing": billing,
    }


def create_renewal(db: Session, user: User, months: int) -> CloudStorageOrder:
    quote = quote_renewal(db, user, months)
    order = CloudStorageOrder(
        user_id=user.id,
        extra_gb=0,
        renewal_months=months,
        total_cents=quote["total_cents"],
        status=CloudStorageOrderStatus.PENDING_PAYMENT,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    pay = AbacatePayService()
    checkout = pay.create_storage_checkout(
        order_id=order.id,
        amount_cents=order.total_cents,
        customer_phone=user.phone,
        description=f"Renovação CyberCloud — {months} mês(es)",
    )
    apply_checkout_result(order, checkout)

    if not pay.payments_required:
        mark_paid(db, order.id)

    db.commit()
    db.refresh(order)
    if order.status == CloudStorageOrderStatus.PENDING_PAYMENT:
        _notify_cloud_pending(db, order)
    return order


def mark_paid(db: Session, order_id: int) -> bool:
    """Credita GB/renovação uma única vez: lock do pedido + usuário, só se ainda estiver pendente."""
    try:
        order = (
            _for_update(
                db.query(CloudStorageOrder).filter(
                    CloudStorageOrder.id == order_id,
                    CloudStorageOrder.status.in_(PAYMENT_RECONCILE_STATUSES),
                ),
                db,
            ).first()
        )
        if not order:
            return False

        user = _for_update(db.query(User).filter(User.id == order.user_id), db).first()
        if not user:
            db.rollback()
            return False

        if order.renewal_months and order.renewal_months >= 1:
            if not user.cloud_paid_until:
                db.rollback()
                raise HTTPException(status_code=400, detail="Assinatura CyberCloud sem vencimento")
            user.cloud_paid_until = extend_paid_until(
                user.cloud_paid_until,
                order.renewal_months,
                user.cloud_billing_day or user.cloud_paid_until.day,
            )
            user.cloud_suspended_for_billing = False
            user.admin_pending_cloud_charge_cents = 0
        elif order.extra_gb > 0:
            apply_subscription_gb(db, user, order.extra_gb, increase_monthly=True)

        order.status = CloudStorageOrderStatus.PAID
        db.commit()
        db.refresh(user)
        _notify_cloud_paid(db, order)
        return True
    except HTTPException:
        db.rollback()
        raise
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            return False
        raise


def sync_all_pending_payments(db: Session, user: User) -> tuple[int, int]:
    """Credita pedidos já pagos na Abacate Pay que ainda estão pendentes no banco."""
    pending = (
        db.query(CloudStorageOrder)
        .filter(
            CloudStorageOrder.user_id == user.id,
            CloudStorageOrder.status == CloudStorageOrderStatus.PENDING_PAYMENT,
        )
        .all()
    )
    reconcile = (
        db.query(CloudStorageOrder)
        .filter(
            CloudStorageOrder.user_id == user.id,
            CloudStorageOrder.status.in_(PAYMENT_RECONCILE_STATUSES),
            CloudStorageOrder.payment_external_id.isnot(None),
        )
        .all()
    )
    if not pending and not reconcile:
        return 0, 0

    pay = AbacatePayService()
    credited = 0
    credited_gb = 0

    if not pay.payments_required:
        for order in pending:
            if mark_paid(db, order.id):
                credited += 1
                credited_gb += order.extra_gb
        return credited, credited_gb

    seen: set[int] = set()
    for order in reconcile:
        if order.id in seen:
            continue
        seen.add(order.id)
        if not order.payment_external_id:
            continue
        try:
            if pay.order_is_paid_at_provider(order, ORDER_KIND_CLOUD) and mark_paid(db, order.id):
                credited += 1
                credited_gb += order.extra_gb
        except HTTPException:
            continue

    return credited, credited_gb


def list_orders(db: Session, user: User) -> list[CloudStorageOrder]:
    return (
        db.query(CloudStorageOrder)
        .filter(CloudStorageOrder.user_id == user.id)
        .order_by(CloudStorageOrder.created_at.desc())
        .all()
    )


def cancel_pending_order(db: Session, user: User, order_id: int) -> None:
    """Cancela o pedido pendente sem apagar a linha, para o webhook ainda reconciliar o Pix."""
    order = _for_update(
        db.query(CloudStorageOrder).filter(
            CloudStorageOrder.id == order_id,
            CloudStorageOrder.user_id == user.id,
            CloudStorageOrder.status == CloudStorageOrderStatus.PENDING_PAYMENT,
        ),
        db,
    ).first()
    if not order:
        existing = db.get(CloudStorageOrder, order_id)
        if not existing or existing.user_id != user.id:
            raise HTTPException(status_code=404, detail="Pedido de armazenamento não encontrado")
        raise HTTPException(
            status_code=400,
            detail="Somente pedidos aguardando pagamento podem ser cancelados",
        )
    order.status = CloudStorageOrderStatus.CANCELLED
    db.commit()


def delete_pending_order(db: Session, user: User, order_id: int) -> None:
    cancel_pending_order(db, user, order_id)


def grant_extra_bytes(db: Session, user: User, extra_gb: int) -> None:
    """Crédito permanente de espaço (cortesia admin, não entra na mensalidade)."""
    if extra_gb <= 0:
        raise HTTPException(status_code=400, detail="Informe GB positivo")
    user.cloud_extra_quota_bytes = int(user.cloud_extra_quota_bytes or 0) + extra_gb * GB_BYTES
    db.commit()
    db.refresh(user)


def sync_payment(db: Session, user: User, order_id: int) -> CloudStorageOrder:
    order = db.get(CloudStorageOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido de armazenamento não encontrado")

    if order.status == CloudStorageOrderStatus.PAID:
        return order

    pay = AbacatePayService()
    if not pay.payments_required:
        if order.status == CloudStorageOrderStatus.PENDING_PAYMENT:
            mark_paid(db, order_id)
            db.refresh(order)
        return order

    if order.status == CloudStorageOrderStatus.PENDING_PAYMENT and not has_live_pix(order):
        description = (
            f"Renovação CyberCloud — {order.renewal_months} mês(es)"
            if order.renewal_months
            else f"+{order.extra_gb} GB CyberCloud/mês"
        )
        checkout = pay.create_storage_checkout(
            order_id=order.id,
            amount_cents=order.total_cents,
            customer_phone=user.phone,
            description=description,
        )
        apply_checkout_result(order, checkout)
        db.commit()
        db.refresh(order)

    if (
        order.status in PAYMENT_RECONCILE_STATUSES
        and order.payment_external_id
        and pay.order_is_paid_at_provider(order, ORDER_KIND_CLOUD)
    ):
        mark_paid(db, order_id)

    db.refresh(order)
    return order
