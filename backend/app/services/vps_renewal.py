"""Aplicação de renovações pagas."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsStatus
from app.services.billing import extend_paid_until
from app.services.provision_progress import update_order_progress

logger = logging.getLogger(__name__)


def apply_renewal_order(db: Session, order: VpsOrder) -> VpsInstance:
    if not order.target_instance_id:
        raise ValueError("Pedido de renovação sem instância alvo")
    if not order.renewal_months or order.renewal_months < 1:
        raise ValueError("Pedido de renovação sem quantidade de meses")

    instance = db.get(VpsInstance, order.target_instance_id)
    if not instance or instance.status == VpsStatus.DELETED:
        raise ValueError("Instância alvo não encontrada")

    if not instance.paid_until:
        raise ValueError("Instância sem data de vencimento configurada")

    if order.status == OrderStatus.ACTIVE or order.provision_step == "ready":
        if order.status != OrderStatus.ACTIVE:
            order.status = OrderStatus.ACTIVE
            order.error_message = None
            db.commit()
        return instance

    update_order_progress(db, order, progress=50, step="configuring")

    instance.paid_until = extend_paid_until(
        instance.paid_until,
        order.renewal_months,
        instance.billing_day,
    )
    instance.suspended_for_billing = False
    instance.error_message = None
    instance.admin_pending_charge_cents = 0

    owner = db.get(User, instance.user_id)
    if owner:
        owner.admin_pending_cloud_charge_cents = 0

    order.status = OrderStatus.ACTIVE
    order.error_message = None
    update_order_progress(db, order, progress=100, step="ready")
    db.commit()
    db.refresh(instance)

    from app.services import host_notify

    host_notify.on_provision_ready(
        db,
        kind="Renovação VPS",
        summary=instance.vm_name or f"pedido #{order.id}",
        customer_user_id=order.user_id,
        client_url="/dashboard",
    )

    logger.info(
        "Renovação aplicada na VPS %s (pedido %s): +%s mês(es), vence em %s",
        instance.vm_name,
        order.id,
        order.renewal_months,
        instance.paid_until,
    )
    return instance


def pending_renewal_order(db: Session, instance_id: int) -> VpsOrder | None:
    return (
        db.query(VpsOrder)
        .filter(
            VpsOrder.target_instance_id == instance_id,
            VpsOrder.order_type == OrderType.RENEWAL,
            VpsOrder.status.in_(
                [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.PROVISIONING]
            ),
        )
        .first()
    )


def resolve_renewal_order_block(db: Session, instance_id: int) -> VpsOrder | None:
    """
    Renovação abandonada (PENDING_PAYMENT) é cancelada.
    Renovação já paga mas não concluída é aplicada agora para não bloquear a próxima.
    """
    pending = pending_renewal_order(db, instance_id)
    if not pending:
        return None
    if pending.status == OrderStatus.PENDING_PAYMENT:
        pending.status = OrderStatus.CANCELLED
        pending.provision_step = "cancelled_new_renewal"
        db.commit()
        return None
    try:
        apply_renewal_order(db, pending)
    except Exception:
        logger.exception("Não foi possível concluir a renovação pendente %s", pending.id)
        return pending
    return None
