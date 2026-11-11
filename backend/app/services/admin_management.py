"""Operações administrativas em contas, VPS e CyberCloud."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.auth import hash_password
from app.models.auth_security import AuthEmailChallenge, AuthMfaTicket, AuthPhoneChallenge, AuthStepUpTicket
from app.models.cloud_file import CloudFile
from app.models.cloud_storage_order import CloudStorageOrder, CloudStorageOrderStatus
from app.models.console_ticket import ConsoleWsTicket
from app.models.coupon import CouponRedemption
from app.models.game_server import GameOrder, GameOrderStatus, GameServer, GameServerStatus
from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsPlan, VpsStatus
from app.models.web_site import WebOrder, WebOrderStatus, WebSite, WebSiteStatus
from app.services.abacatepay import AbacatePayService, apply_checkout_result
from app.services.billing import (
    apply_upgrade_to_custom_monthly,
    calculate_monthly_cents,
    get_billing_snapshot,
    get_cloud_billing_snapshot,
    prorate_monthly_delta,
)
from app.services.cloud_files import delete_all_for_user, quota_info, used_bytes
from app.services.cloud_quota import GB
from app.services.cloud_storage import apply_subscription_gb, quote_purchase
from app.services.hostname import assert_hostname_available, validate_hostname
from app.services.os_templates import get_os_template
from app.services.plan_presets import get_preset, list_plan_presets
from app.services.pricing import (
    calculate_upgrade_monthly_delta,
    calculate_upgrade_quote,
    validate_plan_resources,
)

logger = logging.getLogger(__name__)

_VPS_ORDER_TITLES = {
    "new": "Nova VPS",
    "upgrade": "Upgrade de VPS",
    "renewal": "Renovação de VPS",
    "admin": "Ajuste da equipe",
}
_GAME_LABELS = {
    "samp": "SA-MP",
    "mta": "MTA",
    "minecraft": "Minecraft",
    "fivem": "FiveM",
}


_IN_FLIGHT_ORDER_STATUSES = frozenset({"paid", "provisioning"})
_REMOVABLE_ORDER_KINDS = frozenset({"vps", "cloud", "game", "web"})
_BLOCKED_MACHINE_EVENT_STATUSES = frozenset({"error", "creating", "configuring", "deleted"})


def _status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def order_can_hard_delete(kind: str, status: str, *, linked: bool = False) -> bool:
    if kind not in _REMOVABLE_ORDER_KINDS:
        return False
    if kind in {"vps", "game", "web"} and status in _IN_FLIGHT_ORDER_STATUSES and not linked:
        return False
    return True


def machine_event_can_clear(status: str, *, error_message: str | None, suspended: bool) -> bool:
    if suspended or not error_message:
        return False
    return _status_value(status) not in _BLOCKED_MACHINE_EVENT_STATUSES


def _fmt_date(value: datetime | None) -> str:
    if value is None:
        return "sem data"
    return value.strftime("%d/%m/%Y")


def _fmt_money(cents: int | None) -> str:
    if cents is None:
        return "preço do plano"
    return f"R$ {cents / 100:.2f}".replace(".", ",")


def join_admin_notes(*parts: str | None) -> str | None:
    items = [part.strip() for part in parts if part and str(part).strip()]
    if not items:
        return None
    return " · ".join(items)[:800]


def _add_admin_vps_order(
    db: Session,
    instance: VpsInstance,
    notes: str,
    *,
    total_cents: int = 0,
    status: OrderStatus = OrderStatus.ACTIVE,
) -> VpsOrder:
    plan = _resolve_plan(db, instance)
    order = VpsOrder(
        user_id=instance.user_id,
        plan_id=plan.id,
        vcpu=instance.vcpu,
        ram_mb=instance.ram_mb,
        disk_gb=instance.disk_gb,
        os_template=getattr(instance, "os_template", None) or "sv2016",
        hostname=(instance.vm_name or f"vps-{instance.id}")[:63],
        order_type=OrderType.ADMIN,
        target_instance_id=instance.id,
        total_cents=int(total_cents or 0),
        status=status,
        notes=notes,
        provision_progress=100,
        provision_step="admin",
    )
    db.add(order)
    db.flush()
    return order


def _add_admin_cloud_order(
    db: Session,
    user: User,
    notes: str,
    *,
    extra_gb: int = 0,
    total_cents: int = 0,
    status: CloudStorageOrderStatus = CloudStorageOrderStatus.PAID,
) -> CloudStorageOrder:
    order = CloudStorageOrder(
        user_id=user.id,
        extra_gb=int(extra_gb or 0),
        total_cents=int(total_cents or 0),
        status=status,
        notes=notes,
    )
    db.add(order)
    db.flush()
    return order


def collect_user_orders(db: Session, user_id: int) -> list[dict]:
    items: list[dict] = []
    linked_vps = {
        int(inst.order_id)
        for inst in db.query(VpsInstance).filter(VpsInstance.user_id == user_id).all()
        if getattr(inst, "order_id", None)
    }
    linked_game = {
        int(server.order_id)
        for server in db.query(GameServer).filter(GameServer.user_id == user_id).all()
        if getattr(server, "order_id", None)
    }
    linked_web = {
        int(site.order_id)
        for site in db.query(WebSite).filter(WebSite.user_id == user_id).all()
        if getattr(site, "order_id", None)
    }
    vps_orders = (
        db.query(VpsOrder)
        .filter(VpsOrder.user_id == user_id)
        .order_by(VpsOrder.created_at.desc())
        .all()
    )
    for order in vps_orders:
        kind = _status_value(order.order_type)
        if getattr(order, "notes", None):
            description = order.notes
        elif kind == "new":
            description = (
                f"{order.hostname} · {order.vcpu} vCPU · "
                f"{(order.ram_mb or 0) // 1024} GB RAM · {order.disk_gb} GB"
            )
        elif kind == "renewal":
            months = order.renewal_months or 1
            description = f"{order.hostname} · {months} mês(es)"
        else:
            description = order.hostname
        items.append(
            {
                "kind": "vps",
                "id": order.id,
                "title": _VPS_ORDER_TITLES.get(kind, "Pedido VPS"),
                "description": description,
                "status": _status_value(order.status),
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": order.error_message,
                "can_delete": order_can_hard_delete(
                    "vps",
                    _status_value(order.status),
                    linked=order.id in linked_vps,
                ),
            }
        )

    cloud_orders = (
        db.query(CloudStorageOrder)
        .filter(CloudStorageOrder.user_id == user_id)
        .order_by(CloudStorageOrder.created_at.desc())
        .all()
    )
    for order in cloud_orders:
        renewal = bool(order.renewal_months)
        if getattr(order, "notes", None):
            title = "Ajuste da equipe"
            description = order.notes
        else:
            title = "Renovação CyberCloud" if renewal else "Espaço CyberCloud"
            description = (
                f"{order.renewal_months} mês(es)"
                if renewal
                else f"+{order.extra_gb} GB de armazenamento"
            )
        items.append(
            {
                "kind": "cloud",
                "id": order.id,
                "title": title,
                "description": description,
                "status": _status_value(order.status),
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": None,
                "can_delete": order_can_hard_delete(
                    "cloud",
                    _status_value(order.status),
                    linked=False,
                ),
            }
        )

    game_orders = (
        db.query(GameOrder)
        .filter(GameOrder.user_id == user_id)
        .order_by(GameOrder.created_at.desc())
        .all()
    )
    for order in game_orders:
        game = _status_value(order.game_type)
        items.append(
            {
                "kind": "game",
                "id": order.id,
                "title": f"Servidor {_GAME_LABELS.get(game, game)}",
                "description": (
                    f"{order.server_name} · {order.slots} slots · "
                    f"{(order.ram_mb or 0) // 1024} GB RAM"
                ),
                "status": _status_value(order.status),
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": order.error_message,
                "can_delete": order_can_hard_delete(
                    "game",
                    _status_value(order.status),
                    linked=order.id in linked_game,
                ),
            }
        )

    web_orders = (
        db.query(WebOrder)
        .filter(WebOrder.user_id == user_id)
        .order_by(WebOrder.created_at.desc())
        .all()
    )
    for order in web_orders:
        domain = (order.domain or order.site_slug or "").strip()
        items.append(
            {
                "kind": "web",
                "id": order.id,
                "title": "Hospedagem de site",
                "description": (
                    f"{domain} · {order.ram_mb} MB RAM · {order.disk_mb} MB disco"
                    + (" · PHP" if order.php_enabled else "")
                ),
                "status": _status_value(order.status),
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": order.error_message,
                "can_delete": order_can_hard_delete(
                    "web",
                    _status_value(order.status),
                    linked=order.id in linked_web,
                ),
            }
        )

    items.sort(key=lambda row: row["created_at"] or datetime.min, reverse=True)
    return items[:150]


def delete_admin_order(db: Session, kind: str, order_id: int) -> None:
    normalized = (kind or "").strip().lower()
    if normalized not in _REMOVABLE_ORDER_KINDS:
        raise HTTPException(status_code=400, detail="Tipo de pedido inválido")
    if normalized == "vps":
        _delete_vps_order(db, order_id)
    elif normalized == "cloud":
        _delete_cloud_order(db, order_id)
    elif normalized == "web":
        _delete_web_order(db, order_id)
    else:
        _delete_game_order(db, order_id)
    db.commit()
    logger.info("Admin apagou pedido kind=%s id=%s", normalized, order_id)


def _delete_vps_order(db: Session, order_id: int) -> None:
    order = (
        db.query(VpsOrder)
        .filter(VpsOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    status = _status_value(order.status)
    linked = (
        db.query(VpsInstance)
        .filter(VpsInstance.order_id == order.id)
        .first()
        is not None
    )
    if not order_can_hard_delete("vps", status, linked=linked):
        raise HTTPException(
            status_code=400,
            detail="Pedido ainda em andamento (pago ou em preparação)",
        )
    db.query(VpsInstance).filter(VpsInstance.order_id == order.id).update(
        {VpsInstance.order_id: None},
        synchronize_session=False,
    )
    if status == OrderStatus.PENDING_PAYMENT.value:
        from app.services.coupons import release_coupon_reservation

        release_coupon_reservation(db, order.id, order.coupon_id)
    db.query(CouponRedemption).filter(CouponRedemption.order_id == order.id).delete(
        synchronize_session=False
    )
    db.flush()
    db.delete(order)


def _delete_cloud_order(db: Session, order_id: int) -> None:
    order = (
        db.query(CloudStorageOrder)
        .filter(CloudStorageOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not order_can_hard_delete("cloud", _status_value(order.status), linked=False):
        raise HTTPException(status_code=400, detail="Este pedido não pode ser apagado")
    db.delete(order)


def _delete_game_order(db: Session, order_id: int) -> None:
    order = (
        db.query(GameOrder)
        .filter(GameOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    status = _status_value(order.status)
    linked = (
        db.query(GameServer)
        .filter(GameServer.order_id == order.id)
        .first()
        is not None
    )
    if not order_can_hard_delete("game", status, linked=linked):
        raise HTTPException(
            status_code=400,
            detail="Pedido ainda em andamento (pago ou em preparação)",
        )
    db.query(GameServer).filter(GameServer.order_id == order.id).update(
        {GameServer.order_id: None},
        synchronize_session=False,
    )
    db.flush()
    db.delete(order)


def _delete_web_order(db: Session, order_id: int) -> None:
    order = (
        db.query(WebOrder)
        .filter(WebOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    status = _status_value(order.status)
    linked = (
        db.query(WebSite)
        .filter(WebSite.order_id == order.id)
        .first()
        is not None
    )
    if not order_can_hard_delete("web", status, linked=linked):
        raise HTTPException(
            status_code=400,
            detail="Pedido ainda em andamento (pago ou em preparação)",
        )
    db.query(WebSite).filter(WebSite.order_id == order.id).update(
        {WebSite.order_id: None},
        synchronize_session=False,
    )
    if status == WebOrderStatus.PENDING_PAYMENT.value:
        from app.services.coupons import release_web_coupon_reservation

        release_web_coupon_reservation(db, order.id, order.coupon_id)
    db.query(CouponRedemption).filter(CouponRedemption.web_order_id == order.id).delete(
        synchronize_session=False
    )
    db.flush()
    db.delete(order)


def clear_machine_error_event(db: Session, instance_id: int) -> None:
    instance = db.get(VpsInstance, instance_id)
    if not instance or _status_value(instance.status) == VpsStatus.DELETED.value:
        raise HTTPException(status_code=404, detail="VPS não encontrada")
    if not machine_event_can_clear(
        instance.status,
        error_message=instance.error_message,
        suspended=bool(instance.suspended_for_billing),
    ):
        if instance.suspended_for_billing:
            raise HTTPException(
                status_code=400,
                detail="Suspensão por billing não pode ser apagada aqui. Regularize o vencimento.",
            )
        if _status_value(instance.status) in {"error", "creating", "configuring"}:
            raise HTTPException(
                status_code=400,
                detail="Não é possível ocultar o evento enquanto a VPS está neste estado",
            )
        raise HTTPException(status_code=400, detail="Esta máquina não tem alerta para apagar")
    instance.error_message = None
    db.commit()
    logger.info("Admin limpou alerta da VPS id=%s", instance_id)


def _safe_attachment_name(name: str) -> str:
    return name.replace('"', "").replace("\r", "").replace("\n", "")[:255]


def _resolve_plan(db: Session, instance: VpsInstance) -> VpsPlan:
    if instance.plan_id:
        plan = db.get(VpsPlan, instance.plan_id)
        if plan:
            return plan
    plan = db.query(VpsPlan).filter(VpsPlan.is_active.is_(True)).first()
    if not plan:
        raise HTTPException(status_code=500, detail="Plano VPS não configurado")
    return plan


def get_user_detail(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    q = quota_info(db, user)
    instances = (
        db.query(VpsInstance)
        .filter(VpsInstance.user_id == user_id, VpsInstance.status != VpsStatus.DELETED)
        .order_by(VpsInstance.created_at.desc())
        .all()
    )

    vps_rows = []
    for inst in instances:
        plan = _resolve_plan(db, inst) if inst.plan_id else None
        presets = list_plan_presets(db, plan.id) if plan else []
        monthly = calculate_monthly_cents(plan, inst, plan_presets=presets) if plan else None
        vps_rows.append(
            {
                "id": inst.id,
                "vm_name": inst.vm_name,
                "vcpu": inst.vcpu,
                "ram_mb": inst.ram_mb,
                "disk_gb": inst.disk_gb,
                "status": inst.status.value,
                "ip_address": inst.ip_address,
                "paid_until": inst.paid_until,
                "monthly_cents": monthly,
                "custom_monthly_cents": inst.custom_monthly_cents,
                "admin_pending_charge_cents": int(inst.admin_pending_charge_cents or 0),
                "suspended_for_billing": bool(inst.suspended_for_billing),
            }
        )

    sites = (
        db.query(WebSite)
        .filter(WebSite.user_id == user_id, WebSite.status != WebSiteStatus.DELETED)
        .order_by(WebSite.created_at.desc())
        .all()
    )
    site_rows = []
    for site in sites:
        site_rows.append(
            {
                "id": site.id,
                "site_slug": site.site_slug,
                "domain": site.domain,
                "ram_mb": site.ram_mb,
                "disk_mb": site.disk_mb,
                "php_enabled": bool(site.php_enabled),
                "port": site.port,
                "status": _status_value(site.status),
                "paid_until": site.paid_until,
                "suspended_for_billing": bool(site.suspended_for_billing),
            }
        )

    return {
        "id": user.id,
        "phone": user.phone,
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "mfa_enabled": bool(user.mfa_enabled),
        "created_at": user.created_at,
        "cloud": {
            "used_bytes": q["used_bytes"],
            "quota_bytes": q["quota_bytes"],
            "base_bytes": q["base_bytes"],
            "vps_bonus_bytes": q["vps_bonus_bytes"],
            "subscribed_bytes": q.get("subscribed_bytes", 0),
            "bonus_bytes": q.get("bonus_bytes", 0),
            "extra_bytes": q["extra_bytes"],
            "contracted_gb": q.get("contracted_gb", 0),
            "cloud_paid_until": user.cloud_paid_until,
            "cloud_billing_day": int(user.cloud_billing_day or 1),
            "cloud_monthly_cents": int(user.cloud_monthly_cents or 0),
            "cloud_suspended_for_billing": bool(user.cloud_suspended_for_billing),
            "admin_pending_cloud_charge_cents": int(user.admin_pending_cloud_charge_cents or 0),
            "billing": q.get("billing"),
        },
        "vps_instances": vps_rows,
        "web_sites": site_rows,
        "orders": collect_user_orders(db, user_id),
    }


def delete_web_site(db: Session, admin: User, site_id: int) -> dict:
    from app.services.web_process import destroy_site
    from app.services.web_site_analytics import delete_for_site

    site = db.get(WebSite, site_id)
    if not site or site.status == WebSiteStatus.DELETED:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    delete_for_site(db, site_id)
    message = destroy_site(site)
    db.commit()
    logger.info("Admin %s apagou site id=%s user_id=%s", admin.id, site_id, site.user_id)
    return {"site_id": site_id, "message": message}


def _apply_vps_specs_admin(
    db: Session,
    instance: VpsInstance,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    *,
    apply_vmware: bool,
    monthly_delta: int = 0,
) -> VpsOrder | None:
    needs_change = (
        target_vcpu != instance.vcpu
        or target_ram_mb != instance.ram_mb
        or target_disk_gb != instance.disk_gb
    )
    if not needs_change:
        return None

    if apply_vmware and (
        target_vcpu > instance.vcpu
        or target_ram_mb > instance.ram_mb
        or target_disk_gb > instance.disk_gb
    ):
        order = VpsOrder(
            user_id=instance.user_id,
            plan_id=instance.plan_id,
            vcpu=target_vcpu,
            ram_mb=target_ram_mb,
            disk_gb=target_disk_gb,
            hostname=(instance.vm_name or f"vps-{instance.id}")[:63],
            order_type=OrderType.ADMIN,
            target_instance_id=instance.id,
            total_cents=0,
            status=OrderStatus.PAID,
            provision_progress=100,
            provision_step="admin_applied",
        )
        db.add(order)
        db.flush()
        from app.services.vps_upgrade import apply_upgrade_order

        apply_upgrade_order(db, order)
        db.refresh(instance)
        return order

    instance.vcpu = target_vcpu
    instance.ram_mb = target_ram_mb
    instance.disk_gb = target_disk_gb
    apply_upgrade_to_custom_monthly(instance, monthly_delta)
    db.commit()
    db.refresh(instance)
    return None


def adjust_cloud_quota(
    db: Session,
    user: User,
    extra_gb: int,
    charge_mode: str,
    *,
    note: str | None = None,
) -> dict:
    from app.services.cloud_quota import parse_storage_packages

    packages = parse_storage_packages()
    if not packages:
        raise HTTPException(status_code=400, detail="Nenhum pacote de armazenamento configurado")

    pkg = next((p for p in packages if p["gb"] == extra_gb), None)
    if pkg:
        list_cents = pkg["price_cents"]
    else:
        ref = packages[0]
        list_cents = int(round(ref["price_cents"] / ref["gb"] * extra_gb))

    from app.services.billing import user_cloud_billing_anchor

    paid_until, billing_day = user_cloud_billing_anchor(db, user.id)
    proration = prorate_monthly_delta(list_cents, paid_until, billing_day)
    quote_total = proration["amount_cents"]

    charged = 0
    deferred = 0
    checkout_url = None
    pix_br_code = None
    pix_qr_base64 = None
    pix_expires_at = None
    order_id = None

    if charge_mode == "no_charge":
        apply_subscription_gb(db, user, extra_gb, increase_monthly=False)
        notes = join_admin_notes(
            f"+{extra_gb} GB de CyberCloud",
            "cortesia (sem cobrança)",
            note,
        )
        order = _add_admin_cloud_order(
            db, user, notes or f"+{extra_gb} GB de CyberCloud", extra_gb=extra_gb
        )
        db.commit()
        db.refresh(user)
        order_id = order.id
    elif charge_mode == "defer_renewal":
        apply_subscription_gb(db, user, extra_gb, increase_monthly=True)
        deferred = quote_total
        user.admin_pending_cloud_charge_cents = int(user.admin_pending_cloud_charge_cents or 0) + deferred
        notes = join_admin_notes(
            f"+{extra_gb} GB de CyberCloud",
            f"cobrar na renovação ({_fmt_money(deferred)})",
            note,
        )
        order = _add_admin_cloud_order(
            db,
            user,
            notes or f"+{extra_gb} GB de CyberCloud",
            extra_gb=extra_gb,
            total_cents=deferred,
        )
        db.commit()
        db.refresh(user)
        order_id = order.id
        logger.info(
            "Admin cloud defer user=%s +%sGB R$%.2f na próxima renovação %s",
            user.id,
            extra_gb,
            deferred / 100,
            note or "",
        )
    elif charge_mode == "charge_now":
        order = CloudStorageOrder(
            user_id=user.id,
            extra_gb=extra_gb,
            total_cents=quote_total,
            status=CloudStorageOrderStatus.PENDING_PAYMENT,
            notes=join_admin_notes(
                f"+{extra_gb} GB de CyberCloud",
                f"cobrar agora ({_fmt_money(quote_total)})",
                note,
            ),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        pay = AbacatePayService()
        checkout = pay.create_storage_checkout(
            order_id=order.id,
            amount_cents=order.total_cents,
            customer_phone=user.phone,
            description=f"+{extra_gb} GB CyberCloud (admin)",
        )
        apply_checkout_result(order, checkout)
        if not pay.payments_required:
            from app.services.cloud_storage import mark_paid

            mark_paid(db, order.id)
        else:
            db.commit()
        db.refresh(order)
        charged = order.total_cents
        checkout_url = order.payment_checkout_url
        pix_br_code = order.pix_br_code
        pix_qr_base64 = order.pix_qr_base64
        pix_expires_at = order.pix_expires_at
        order_id = order.id
    else:
        raise HTTPException(status_code=400, detail="Modo de cobrança inválido")

    detail = get_user_detail(db, user.id)
    return {
        "extra_gb_added": extra_gb,
        "charge_mode": charge_mode,
        "charged_cents": charged,
        "deferred_cents": deferred,
        "checkout_url": checkout_url,
        "pix_br_code": pix_br_code,
        "pix_qr_base64": pix_qr_base64,
        "pix_expires_at": pix_expires_at,
        "order_id": order_id,
        "cloud": detail["cloud"],
    }


def update_vps_admin(
    db: Session,
    instance: VpsInstance,
    *,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    charge_mode: str,
    apply_vmware: bool = True,
    paid_until: datetime | None = None,
    clear_suspension: bool = False,
) -> dict:
    plan = _resolve_plan(db, instance)
    presets = list_plan_presets(db, plan.id)
    validate_plan_resources(plan, target_vcpu, target_ram_mb, target_disk_gb)

    monthly_delta = 0
    proration = None
    charge_cents = 0
    try:
        quote = calculate_upgrade_quote(
            plan,
            instance,
            target_vcpu,
            target_ram_mb,
            target_disk_gb,
            plan_presets=presets,
        )
        monthly_delta = quote["monthly_delta_cents"]
        charge_cents = quote["total_cents"]
        proration = {
            "monthly_delta_cents": quote["monthly_delta_cents"],
            "amount_cents": quote["total_cents"],
            "days_remaining": quote["days_remaining"],
            "period_days": quote["period_days"],
            "prorated": quote["prorated"],
        }
    except HTTPException as exc:
        detail = str(exc.detail)
        if "Downgrade" in detail or "alterado" in detail:
            if (
                target_vcpu == instance.vcpu
                and target_ram_mb == instance.ram_mb
                and target_disk_gb == instance.disk_gb
            ):
                raise
        else:
            raise

    if charge_mode == "no_charge":
        charge_cents = 0
    charged = 0
    deferred = 0
    checkout_url = None
    order_id = None

    spec_parts: list[str] = []
    if target_vcpu != instance.vcpu:
        spec_parts.append(f"vCPU {instance.vcpu} → {target_vcpu}")
    if target_ram_mb != instance.ram_mb:
        spec_parts.append(f"RAM {instance.ram_mb // 1024} GB → {target_ram_mb // 1024} GB")
    if target_disk_gb != instance.disk_gb:
        spec_parts.append(f"disco {instance.disk_gb} GB → {target_disk_gb} GB")
    if paid_until is not None and paid_until != instance.paid_until:
        spec_parts.append(f"vencimento {_fmt_date(instance.paid_until)} → {_fmt_date(paid_until)}")
    if clear_suspension and instance.suspended_for_billing:
        spec_parts.append("removeu suspensão de billing")
    if charge_mode == "no_charge" and spec_parts:
        spec_parts.append("cortesia (sem cobrança)")
    elif charge_mode == "defer_renewal" and charge_cents > 0:
        spec_parts.append(f"cobrar na renovação ({_fmt_money(charge_cents)})")
    elif charge_mode == "charge_now" and charge_cents > 0:
        spec_parts.append(f"cobrar agora ({_fmt_money(charge_cents)})")
    notes = join_admin_notes(*spec_parts)

    if charge_mode == "defer_renewal" and charge_cents > 0:
        deferred = charge_cents
        instance.admin_pending_charge_cents = int(instance.admin_pending_charge_cents or 0) + deferred
    elif charge_mode == "charge_now" and charge_cents > 0:
        owner = db.get(User, instance.user_id)
        order = VpsOrder(
            user_id=instance.user_id,
            plan_id=plan.id,
            vcpu=target_vcpu,
            ram_mb=target_ram_mb,
            disk_gb=target_disk_gb,
            hostname=(instance.vm_name or f"vps-{instance.id}")[:63],
            order_type=OrderType.UPGRADE,
            target_instance_id=instance.id,
            total_cents=charge_cents,
            upgrade_monthly_delta_cents=monthly_delta,
            status=OrderStatus.PENDING_PAYMENT,
            notes=notes or f"Upgrade admin {instance.vm_name}",
        )
        db.add(order)
        db.flush()
        from app.api.orders import _attach_checkout

        _attach_checkout(
            db,
            order,
            owner,
            f"Upgrade admin {instance.vm_name}",
            None,
            commit=False,
        )
        db.commit()
        db.refresh(order)
        charged = charge_cents
        checkout_url = order.payment_checkout_url
        order_id = order.id
        return {
            "instance_id": instance.id,
            "charge_mode": charge_mode,
            "charged_cents": charged,
            "deferred_cents": 0,
            "checkout_url": checkout_url,
            "pix_br_code": order.pix_br_code,
            "pix_qr_base64": order.pix_qr_base64,
            "pix_expires_at": order.pix_expires_at,
            "order_id": order_id,
            "proration": proration,
            "vcpu": instance.vcpu,
            "ram_mb": instance.ram_mb,
            "disk_gb": instance.disk_gb,
        }

    if paid_until is not None:
        instance.paid_until = paid_until
    if clear_suspension:
        instance.suspended_for_billing = False

    spec_order = _apply_vps_specs_admin(
        db,
        instance,
        target_vcpu,
        target_ram_mb,
        target_disk_gb,
        apply_vmware=apply_vmware,
        monthly_delta=monthly_delta,
    )
    db.refresh(instance)

    if notes:
        if spec_order:
            spec_order.notes = notes
            spec_order.order_type = OrderType.ADMIN
            order_id = spec_order.id
        else:
            ledger = _add_admin_vps_order(
                db, instance, notes, total_cents=deferred
            )
            order_id = ledger.id
        db.commit()

    return {
        "instance_id": instance.id,
        "charge_mode": charge_mode,
        "charged_cents": charged,
        "deferred_cents": deferred,
        "checkout_url": checkout_url,
        "order_id": order_id,
        "proration": proration,
        "vcpu": instance.vcpu,
        "ram_mb": instance.ram_mb,
        "disk_gb": instance.disk_gb,
    }


def update_vps_billing(
    db: Session,
    instance: VpsInstance,
    *,
    paid_until: datetime | None = None,
    clear_suspension: bool = False,
    clear_pending_charge: bool = False,
    custom_monthly_cents: int | None = None,
    _clear_custom_monthly: bool = False,
) -> dict:
    parts: list[str] = []
    if paid_until is not None and paid_until != instance.paid_until:
        parts.append(f"vencimento {_fmt_date(instance.paid_until)} → {_fmt_date(paid_until)}")
        instance.paid_until = paid_until
        instance.billing_day = paid_until.day
    if clear_suspension and instance.suspended_for_billing:
        parts.append("removeu suspensão de billing")
        instance.suspended_for_billing = False
    elif clear_suspension:
        instance.suspended_for_billing = False
    if clear_pending_charge and int(instance.admin_pending_charge_cents or 0) > 0:
        parts.append("zerou cobrança pendente na renovação")
        instance.admin_pending_charge_cents = 0
    elif clear_pending_charge:
        instance.admin_pending_charge_cents = 0
    if _clear_custom_monthly:
        if instance.custom_monthly_cents is not None:
            parts.append(
                f"valor mensal {_fmt_money(instance.custom_monthly_cents)} → preço do plano"
            )
        instance.custom_monthly_cents = None
    elif custom_monthly_cents is not None and custom_monthly_cents != instance.custom_monthly_cents:
        parts.append(
            f"valor mensal {_fmt_money(instance.custom_monthly_cents)} → {_fmt_money(custom_monthly_cents)}"
        )
        instance.custom_monthly_cents = custom_monthly_cents

    notes = join_admin_notes(*parts)
    if notes:
        _add_admin_vps_order(db, instance, notes)

    db.commit()
    db.refresh(instance)
    plan = _resolve_plan(db, instance)
    presets = list_plan_presets(db, plan.id)
    monthly = calculate_monthly_cents(plan, instance, plan_presets=presets)
    billing = get_billing_snapshot(instance, monthly_cents=monthly)
    return {
        "id": instance.id,
        "paid_until": instance.paid_until,
        "admin_pending_charge_cents": instance.admin_pending_charge_cents,
        "suspended_for_billing": instance.suspended_for_billing,
        "custom_monthly_cents": instance.custom_monthly_cents,
        "billing": billing,
    }


def update_cloud_billing(
    db: Session,
    user: User,
    *,
    paid_until: datetime | None = None,
    cloud_contracted_gb: int | None = None,
    cloud_monthly_cents: int | None = None,
    clear_suspension: bool = False,
    clear_pending_charge: bool = False,
) -> dict:
    parts: list[str] = []
    if paid_until is not None and paid_until != user.cloud_paid_until:
        parts.append(f"vencimento {_fmt_date(user.cloud_paid_until)} → {_fmt_date(paid_until)}")
        user.cloud_paid_until = paid_until
        user.cloud_billing_day = paid_until.day
    if cloud_contracted_gb is not None and cloud_contracted_gb != int(user.cloud_contracted_gb or 0):
        parts.append(f"espaço contratado {int(user.cloud_contracted_gb or 0)} GB → {cloud_contracted_gb} GB")
        user.cloud_contracted_gb = cloud_contracted_gb
    if cloud_monthly_cents is not None and cloud_monthly_cents != int(user.cloud_monthly_cents or 0):
        parts.append(
            f"mensalidade {_fmt_money(int(user.cloud_monthly_cents or 0))} → {_fmt_money(cloud_monthly_cents)}"
        )
        user.cloud_monthly_cents = cloud_monthly_cents
    if clear_suspension and user.cloud_suspended_for_billing:
        parts.append("removeu suspensão de billing")
        user.cloud_suspended_for_billing = False
    elif clear_suspension:
        user.cloud_suspended_for_billing = False
    if clear_pending_charge and int(user.admin_pending_cloud_charge_cents or 0) > 0:
        parts.append("zerou cobrança pendente na renovação")
        user.admin_pending_cloud_charge_cents = 0
    elif clear_pending_charge:
        user.admin_pending_cloud_charge_cents = 0

    notes = join_admin_notes(*parts)
    if notes:
        _add_admin_cloud_order(db, user, notes)

    db.commit()
    db.refresh(user)
    detail = get_user_detail(db, user.id)
    return {"user_id": user.id, "cloud": detail["cloud"]}


def collect_deletion_preview(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    instances = (
        db.query(VpsInstance)
        .filter(VpsInstance.user_id == user_id, VpsInstance.status != VpsStatus.DELETED)
        .order_by(VpsInstance.created_at.desc())
        .all()
    )
    games = (
        db.query(GameServer)
        .filter(GameServer.user_id == user_id, GameServer.status != GameServerStatus.DELETED)
        .order_by(GameServer.created_at.desc())
        .all()
    )
    web_sites = (
        db.query(WebSite)
        .filter(WebSite.user_id == user_id, WebSite.status != WebSiteStatus.DELETED)
        .order_by(WebSite.created_at.desc())
        .all()
    )
    cloud_files_count = (
        db.query(CloudFile)
        .filter(CloudFile.user_id == user_id, CloudFile.is_folder.is_(False))
        .count()
    )
    cloud_folders_count = (
        db.query(CloudFile)
        .filter(CloudFile.user_id == user_id, CloudFile.is_folder.is_(True))
        .count()
    )
    vps_orders = db.query(VpsOrder).filter(VpsOrder.user_id == user_id).count()
    cloud_orders = db.query(CloudStorageOrder).filter(CloudStorageOrder.user_id == user_id).count()
    game_orders = db.query(GameOrder).filter(GameOrder.user_id == user_id).count()
    web_orders = db.query(WebOrder).filter(WebOrder.user_id == user_id).count()
    pending = (
        db.query(VpsOrder)
        .filter(VpsOrder.user_id == user_id, VpsOrder.status == OrderStatus.PENDING_PAYMENT)
        .count()
        + db.query(CloudStorageOrder)
        .filter(
            CloudStorageOrder.user_id == user_id,
            CloudStorageOrder.status == CloudStorageOrderStatus.PENDING_PAYMENT,
        )
        .count()
        + db.query(GameOrder)
        .filter(GameOrder.user_id == user_id, GameOrder.status == GameOrderStatus.PENDING_PAYMENT)
        .count()
        + db.query(WebOrder)
        .filter(WebOrder.user_id == user_id, WebOrder.status == WebOrderStatus.PENDING_PAYMENT)
        .count()
    )

    warnings: list[str] = []
    if user.is_admin:
        warnings.append("Esta conta é administradora.")
    if pending:
        warnings.append(f"Há {pending} pedido(s) aguardando pagamento.")
    if instances:
        warnings.append(
            f"{len(instances)} VPS será(ão) desligada(s) e apagada(s) no ESXi."
        )
    if games:
        warnings.append(f"{len(games)} servidor(es) de jogo será(ão) parado(s) e apagado(s).")
    if web_sites:
        warnings.append(f"{len(web_sites)} site(s) será(ão) parado(s) e apagado(s).")
    if cloud_files_count or cloud_folders_count:
        warnings.append("Arquivos e pastas do CyberCloud serão apagados (incluindo cópias no Discord).")

    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "vps": [
            {
                "id": inst.id,
                "vm_name": inst.vm_name,
                "status": _status_value(inst.status),
                "ip_address": inst.ip_address,
                "vcpu": inst.vcpu,
                "ram_mb": inst.ram_mb,
                "disk_gb": inst.disk_gb,
            }
            for inst in instances
        ],
        "game_servers": [
            {
                "id": server.id,
                "server_name": server.server_name,
                "game_type": _status_value(server.game_type),
                "status": _status_value(server.status),
                "port": server.port,
            }
            for server in games
        ],
        "web_sites": [
            {
                "id": site.id,
                "site_slug": site.site_slug,
                "domain": site.domain,
                "status": _status_value(site.status),
                "port": site.port,
            }
            for site in web_sites
        ],
        "cloud": {
            "files": cloud_files_count,
            "folders": cloud_folders_count,
            "used_bytes": used_bytes(db, user.id),
        },
        "orders": {
            "vps": vps_orders,
            "cloud": cloud_orders,
            "game": game_orders,
            "web": web_orders,
            "pending_payment": pending,
        },
        "warnings": warnings,
    }


def _assert_can_delete_account(db: Session, admin: User, user: User, confirm_phone: str) -> None:
    from app.utils.phone import normalize_phone

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir a própria conta")
    if user.is_admin:
        other_admins = (
            db.query(User)
            .filter(User.is_admin.is_(True), User.is_active.is_(True), User.id != user.id)
            .count()
        )
        if other_admins < 1:
            raise HTTPException(
                status_code=400,
                detail="Não é possível excluir o último administrador ativo",
            )
    try:
        expected = normalize_phone(user.phone)
        provided = normalize_phone(confirm_phone)
    except Exception:
        raise HTTPException(status_code=400, detail="Confirme o telefone da conta para excluir") from None
    if provided != expected:
        raise HTTPException(status_code=400, detail="Confirme o telefone da conta para excluir")


def _purge_game_data(server: GameServer) -> None:
    from app.config import get_settings
    from app.services.game_sandbox import is_under_root

    raw = (server.data_path or "").strip()
    if not raw:
        return
    data = Path(raw).resolve()
    roots = [Path(get_settings().game_servers_data_path).resolve()]
    host = getattr(server, "host", None)
    if host is not None and getattr(host, "data_path", None):
        roots.append(Path(host.data_path).resolve())
    if any(is_under_root(data, root) for root in roots):
        shutil.rmtree(data, ignore_errors=True)


def _purge_user_game_root(user_id: int, servers: list[GameServer]) -> None:
    from app.config import get_settings
    from app.services.game_sandbox import is_under_root

    roots = {Path(get_settings().game_servers_data_path).resolve()}
    for server in servers:
        host = getattr(server, "host", None)
        if host is not None and getattr(host, "data_path", None):
            roots.add(Path(host.data_path).resolve())
    for root in roots:
        user_dir = root / str(int(user_id))
        if user_dir.exists() and is_under_root(user_dir, root):
            shutil.rmtree(user_dir, ignore_errors=True)


def _purge_account_rows(db: Session, user: User) -> None:
    order_ids = [row[0] for row in db.query(VpsOrder.id).filter(VpsOrder.user_id == user.id).all()]
    if order_ids:
        db.query(CouponRedemption).filter(CouponRedemption.order_id.in_(order_ids)).delete(
            synchronize_session=False
        )
    db.query(VpsOrder).filter(VpsOrder.user_id == user.id).update(
        {VpsOrder.target_instance_id: None},
        synchronize_session=False,
    )
    db.flush()
    db.query(GameServer).filter(GameServer.user_id == user.id).delete(synchronize_session=False)
    db.query(GameOrder).filter(GameOrder.user_id == user.id).delete(synchronize_session=False)
    db.query(WebSite).filter(WebSite.user_id == user.id).delete(synchronize_session=False)
    db.query(WebOrder).filter(WebOrder.user_id == user.id).delete(synchronize_session=False)
    db.query(CloudStorageOrder).filter(CloudStorageOrder.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(VpsInstance).filter(VpsInstance.user_id == user.id).delete(synchronize_session=False)
    db.flush()
    db.query(VpsOrder).filter(VpsOrder.user_id == user.id).delete(synchronize_session=False)
    db.query(AuthMfaTicket).filter(AuthMfaTicket.user_id == user.id).delete(synchronize_session=False)
    db.query(AuthStepUpTicket).filter(AuthStepUpTicket.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(ConsoleWsTicket).filter(ConsoleWsTicket.user_id == user.id).delete(
        synchronize_session=False
    )
    if user.phone:
        db.query(AuthPhoneChallenge).filter(AuthPhoneChallenge.phone == user.phone).delete(
            synchronize_session=False
        )
    if user.email:
        db.query(AuthEmailChallenge).filter(AuthEmailChallenge.email == user.email).delete(
            synchronize_session=False
        )
    db.flush()


def _destroy_vps_instance(instance: VpsInstance) -> str:
    from app.services.vps_actions import destroy_instance

    return destroy_instance(instance)


def _stop_game_server(server: GameServer) -> None:
    from app.services.game_process import stop_server

    stop_server(server)


def delete_user_account(db: Session, admin: User, user_id: int, confirm_phone: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    _assert_can_delete_account(db, admin, user, confirm_phone)

    instances = db.query(VpsInstance).filter(VpsInstance.user_id == user_id).all()
    destroyed: list[str] = []
    failed: list[str] = []
    for instance in instances:
        name = instance.vm_name or f"vps-{instance.id}"
        try:
            _destroy_vps_instance(instance)
            destroyed.append(name)
        except Exception as exc:
            logger.warning(
                "Falha ao destruir VM user_id=%s vm=%s (%s)",
                user_id,
                name,
                type(exc).__name__,
            )
            failed.append(name)
    if failed:
        raise HTTPException(
            status_code=409,
            detail=(
                "Não foi possível apagar todas as VMs no ESXi. A conta não foi excluída. "
                f"Falhou: {', '.join(failed)}."
            ),
        )

    servers = (
        db.query(GameServer)
        .options(joinedload(GameServer.host))
        .filter(GameServer.user_id == user_id)
        .all()
    )
    stopped = 0
    for server in servers:
        if server.status != GameServerStatus.DELETED:
            try:
                _stop_game_server(server)
            except Exception:
                logger.warning("Falha ao parar game server_id=%s user_id=%s", server.id, user_id)
            _purge_game_data(server)
            stopped += 1
        server.status = GameServerStatus.DELETED
        server.process_pid = None
    _purge_user_game_root(user_id, servers)

    sites = (
        db.query(WebSite)
        .filter(WebSite.user_id == user_id, WebSite.status != WebSiteStatus.DELETED)
        .all()
    )
    deleted_sites = 0
    for site in sites:
        try:
            from app.services.web_process import destroy_site
            from app.services.web_site_analytics import delete_for_site

            delete_for_site(db, site.id)
            destroy_site(site)
            deleted_sites += 1
        except Exception:
            logger.warning("Falha ao apagar site id=%s user_id=%s", site.id, user_id)

    cloud_deleted = delete_all_for_user(db, user)
    _purge_account_rows(db, user)
    db.delete(user)
    db.commit()
    logger.info(
        "Admin %s excluiu conta user_id=%s vms=%s games=%s sites=%s cloud=%s",
        admin.id,
        user_id,
        len(destroyed),
        stopped,
        deleted_sites,
        cloud_deleted,
    )
    return {
        "deleted_user_id": user_id,
        "destroyed_vms": destroyed,
        "stopped_game_servers": stopped,
        "deleted_web_sites": deleted_sites,
        "deleted_cloud_files": cloud_deleted,
    }


def create_panel_user(
    db: Session,
    *,
    phone: str,
    email: str,
    name: str,
    password: str,
    is_admin: bool = False,
) -> User:
    email_norm = (email or "").strip().lower()
    if not email_norm or "@" not in email_norm:
        raise HTTPException(status_code=400, detail="Informe um e-mail válido")
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(status_code=400, detail="Telefone já cadastrado")
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = User(
        phone=phone,
        email=email_norm,
        name=name.strip(),
        hashed_password=hash_password(password),
        is_admin=bool(is_admin),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_courtesy_vps_order(
    db: Session,
    *,
    user_id: int,
    hostname: str,
    os_template: str = "sv2016",
    plan_id: int | None = None,
    preset_id: int | None = None,
    vcpu: int = 2,
    ram_mb: int = 4096,
    disk_gb: int = 40,
) -> VpsOrder:
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Selecione uma conta ativa")
    try:
        hostname = validate_hostname(hostname)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        os_def = get_os_template(os_template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan = db.get(VpsPlan, plan_id) if plan_id else None
    if plan is None or not plan.is_active:
        plan = db.query(VpsPlan).filter(VpsPlan.is_active.is_(True)).order_by(VpsPlan.id.asc()).first()
    if plan is None:
        raise HTTPException(status_code=500, detail="Plano VPS não configurado")

    preset = None
    if preset_id:
        preset = get_preset(db, preset_id, plan.id)
        if not preset:
            raise HTTPException(status_code=404, detail="Plano predefinido não encontrado")
        vcpu = preset.vcpu
        ram_mb = preset.ram_mb
        disk_gb = preset.disk_gb

    disk_gb = max(int(disk_gb), int(plan.default_disk_gb or 30), 30)
    validate_plan_resources(plan, int(vcpu), int(ram_mb), disk_gb)
    assert_hostname_available(db, hostname)

    order = VpsOrder(
        user_id=user.id,
        plan_id=plan.id,
        vcpu=int(vcpu),
        ram_mb=int(ram_mb),
        disk_gb=disk_gb,
        os_template=os_def.slug,
        hostname=hostname,
        order_type=OrderType.ADMIN,
        subtotal_cents=0,
        discount_cents=0,
        total_cents=0,
        status=OrderStatus.PAID,
        notes="VM criada pelo painel admin",
        provision_progress=5,
        provision_step="payment_confirmed",
    )
    db.add(order)
    db.flush()
    return order
