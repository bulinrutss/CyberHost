"""Renovação de hospedagem de sites."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.web_site import WebOrder, WebOrderStatus, WebOrderType, WebSite, WebSiteStatus
from app.services.billing import extend_paid_until, quote_web_renewal_price
from app.services.web_plan_presets import get_preset

logger = logging.getLogger(__name__)


def resolve_web_monthly_cents(db: Session, site: WebSite) -> int:
    order = site.order
    if order and order.total_cents and order.total_cents > 0:
        return int(order.total_cents)
    if order and order.preset_id:
        preset = get_preset(db, order.preset_id)
        if preset:
            return int(preset.price_cents)
    return 0


def apply_web_renewal_order(db: Session, order: WebOrder) -> WebSite:
    if order.order_type != WebOrderType.RENEWAL:
        raise ValueError("Pedido não é renovação de site")
    if not order.target_site_id:
        raise ValueError("Pedido de renovação sem site alvo")
    if not order.renewal_months or order.renewal_months < 1:
        raise ValueError("Pedido de renovação sem quantidade de meses")

    site = db.get(WebSite, order.target_site_id)
    if not site or site.status == WebSiteStatus.DELETED:
        raise ValueError("Site alvo não encontrado")
    if site.user_id != order.user_id:
        raise ValueError("Site não pertence ao cliente do pedido")
    if not site.paid_until:
        raise ValueError("Site sem data de vencimento configurada")

    if order.status == WebOrderStatus.ACTIVE or order.provision_step == "ready":
        if order.status != WebOrderStatus.ACTIVE:
            order.status = WebOrderStatus.ACTIVE
            order.error_message = None
            db.commit()
        return site

    order.provision_progress = 50
    order.provision_step = "configuring"

    site.paid_until = extend_paid_until(
        site.paid_until,
        order.renewal_months,
        site.billing_day,
    )
    was_suspended = bool(site.suspended_for_billing)
    site.suspended_for_billing = False
    site.error_message = None

    order.status = WebOrderStatus.ACTIVE
    order.error_message = None
    order.provision_progress = 100
    order.provision_step = "ready"
    db.commit()
    db.refresh(site)

    if was_suspended or site.status == WebSiteStatus.STOPPED:
        from app.services import web_process

        try:
            web_process.start_site(site)
            db.commit()
        except Exception:
            logger.exception("Renovação ok, mas não foi possível ligar o site %s", site.id)

    from app.services import host_notify

    host_notify.on_provision_ready(
        db,
        kind="Renovação site",
        summary=site.domain or site.site_slug,
        customer_user_id=order.user_id,
        client_url=f"/dashboard/sites/{site.id}",
    )

    logger.info(
        "Renovação aplicada no site %s (pedido %s): +%s mês(es), vence em %s",
        site.site_slug,
        order.id,
        order.renewal_months,
        site.paid_until,
    )
    return site


def pending_web_renewal_order(db: Session, site_id: int) -> WebOrder | None:
    return (
        db.query(WebOrder)
        .filter(
            WebOrder.target_site_id == site_id,
            WebOrder.order_type == WebOrderType.RENEWAL,
            WebOrder.status.in_(
                (
                    WebOrderStatus.PENDING_PAYMENT,
                    WebOrderStatus.PAID,
                    WebOrderStatus.PROVISIONING,
                )
            ),
        )
        .first()
    )


def resolve_web_renewal_order_block(db: Session, site_id: int) -> WebOrder | None:
    pending = pending_web_renewal_order(db, site_id)
    if not pending:
        return None
    if pending.status == WebOrderStatus.PENDING_PAYMENT:
        pending.status = WebOrderStatus.CANCELLED
        pending.provision_step = "cancelled_new_renewal"
        db.commit()
        return None
    try:
        apply_web_renewal_order(db, pending)
    except Exception:
        logger.exception("Não foi possível concluir a renovação pendente %s", pending.id)
        return pending
    return None


def quote_site_renewal(db: Session, site: WebSite, months: int) -> dict:
    monthly = resolve_web_monthly_cents(db, site)
    quote = quote_web_renewal_price(monthly, months)
    new_paid_until = extend_paid_until(site.paid_until, months, site.billing_day)
    billing = get_web_billing_snapshot_for_site(db, site, monthly_cents=monthly)
    return {
        **quote,
        "paid_until": site.paid_until,
        "new_paid_until": new_paid_until,
        "billing": billing,
    }


def get_web_billing_snapshot_for_site(db: Session, site: WebSite, *, monthly_cents: int | None = None):
    from app.services.billing import get_web_billing_snapshot

    monthly = monthly_cents if monthly_cents is not None else resolve_web_monthly_cents(db, site)
    return get_web_billing_snapshot(site, monthly_cents=monthly)
