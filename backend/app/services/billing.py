"""Vencimento mensal, carência e preço recorrente."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from app.models.vps import VpsInstance, VpsPlan, VpsPlanPreset
from app.services.pricing import compute_monthly_price, resolve_monthly_price

GRACE_DAYS = 3
MAX_RENEWAL_MONTHS = 12
MAX_RENEWAL_DISCOUNT_PERCENT = 20


def renewal_discount_percent(months: int) -> float:
    """Desconto progressivo desde 1 mês até 20% em 12 meses (independente do vencimento)."""
    if months < 1:
        return 0.0
    capped = min(months, MAX_RENEWAL_MONTHS)
    return capped / MAX_RENEWAL_MONTHS * MAX_RENEWAL_DISCOUNT_PERCENT


def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)


def next_billing_date(from_dt: datetime, billing_day: int) -> datetime:
    """Próximo vencimento: mesmo dia no mês seguinte (ajusta fim de mês)."""
    year, month = from_dt.year, from_dt.month + 1
    if month > 12:
        month = 1
        year += 1
    day = min(billing_day, calendar.monthrange(year, month)[1])
    return _end_of_day(from_dt.replace(year=year, month=month, day=day))


def initial_paid_until(start: datetime | None = None) -> tuple[datetime, int]:
    """Primeiro vencimento: mesmo dia no próximo mês."""
    start = start or datetime.utcnow()
    billing_day = start.day
    return next_billing_date(start, billing_day), billing_day


def extend_paid_until(current_paid_until: datetime, months: int, billing_day: int) -> datetime:
    """Estende a partir do vencimento atual (permite renovar antes e empilhar meses)."""
    if months < 1:
        raise ValueError("months deve ser >= 1")
    result = current_paid_until
    for _ in range(months):
        result = next_billing_date(result, billing_day)
    return result


def calculate_monthly_cents(
    plan: VpsPlan | None,
    instance: VpsInstance,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> int:
    if getattr(instance, "custom_monthly_cents", None) is not None:
        return int(instance.custom_monthly_cents)  # type: ignore[arg-type]
    if not plan:
        return 0
    disk_gb = instance.disk_gb or plan.default_disk_gb
    if plan_presets is not None:
        return resolve_monthly_price(
            plan, instance.vcpu, instance.ram_mb, disk_gb, plan_presets=plan_presets
        )
    return compute_monthly_price(plan, instance.vcpu, instance.ram_mb, disk_gb)


def previous_billing_date(from_dt: datetime, billing_day: int) -> datetime:
    """Início do ciclo de cobrança que termina em ``from_dt`` (vencimento)."""
    year, month = from_dt.year, from_dt.month - 1
    if month < 1:
        month = 12
        year -= 1
    day = min(billing_day, calendar.monthrange(year, month)[1])
    return _end_of_day(from_dt.replace(year=year, month=month, day=day))


def _billing_cycle_end_date(paid_until: datetime, now: datetime) -> date:
    """Próximo vencimento do ciclo mensal (no dia do vencimento, usa o mês seguinte)."""
    billing_day = paid_until.day
    today = now.date()
    due = paid_until.date()
    if today > due:
        return due

    year, month = today.year, today.month
    day = min(billing_day, calendar.monthrange(year, month)[1])
    end = date(year, month, day)
    # No dia do vencimento (end == today), o ciclo atual vai até o próximo mês.
    if end <= today:
        month += 1
        if month > 12:
            month, year = 1, year + 1
        day = min(billing_day, calendar.monthrange(year, month)[1])
        end = date(year, month, day)
    return min(end, due)


def prorate_monthly_delta(
    monthly_delta_cents: int,
    paid_until: datetime | None,
    billing_day: int | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """
    Calcula o valor proporcional ao tempo restante até a renovação (``paid_until``).
    Soma cada ciclo mensal até o vencimento, com fração no ciclo corrente.
    """
    _ = billing_day
    now = now or datetime.utcnow()

    if not paid_until or monthly_delta_cents <= 0:
        return {
            "amount_cents": monthly_delta_cents,
            "monthly_delta_cents": monthly_delta_cents,
            "days_remaining": 0,
            "period_days": 30,
            "prorated": False,
        }

    billing_day = paid_until.day
    today = now.date()
    due = paid_until.date()

    if today > due:
        return {
            "amount_cents": monthly_delta_cents,
            "monthly_delta_cents": monthly_delta_cents,
            "days_remaining": 0,
            "period_days": 30,
            "prorated": False,
        }

    days_remaining = max(0, (due - today).days)
    month_days = 30
    total = 0.0
    cursor = now
    for _ in range(24):
        if cursor.date() >= due:
            break
        cycle_end = _billing_cycle_end_date(paid_until, cursor)
        if cycle_end <= cursor.date():
            break
        cycle_end_dt = _end_of_day(datetime.combine(cycle_end, paid_until.time()))
        period_start = previous_billing_date(cycle_end_dt, billing_day)
        period_days = max(1, (cycle_end - period_start.date()).days)
        slice_days = max(0, (cycle_end - cursor.date()).days)
        if slice_days <= 0:
            break
        if total == 0.0:
            month_days = period_days
        total += monthly_delta_cents * slice_days / period_days
        cursor = cycle_end_dt

    if days_remaining <= 0:
        amount = max(1, round(monthly_delta_cents / month_days))
        prorated = True
    else:
        amount = max(1, round(total)) if total > 0 else max(
            1, round(monthly_delta_cents * days_remaining / month_days)
        )
        prorated = amount != monthly_delta_cents

    return {
        "amount_cents": amount,
        "monthly_delta_cents": monthly_delta_cents,
        "days_remaining": days_remaining,
        "period_days": month_days,
        "prorated": prorated,
    }


def apply_upgrade_to_custom_monthly(instance: VpsInstance, monthly_delta_cents: int) -> None:
    """Soma acréscimo do upgrade ao valor personalizado de renovação."""
    if monthly_delta_cents <= 0:
        return
    if instance.custom_monthly_cents is not None:
        instance.custom_monthly_cents = int(instance.custom_monthly_cents) + monthly_delta_cents


def user_cloud_billing_anchor(db, user_id: int) -> tuple[datetime | None, int]:
    """Referência de vencimento para prorrata do CyberCloud (maior paid_until das VPS ativas)."""
    from app.models.vps import VpsInstance, VpsStatus

    instances = (
        db.query(VpsInstance)
        .filter(
            VpsInstance.user_id == user_id,
            VpsInstance.status != VpsStatus.DELETED,
            VpsInstance.paid_until.isnot(None),
        )
        .all()
    )
    if not instances:
        return None, 1
    latest = max(instances, key=lambda i: i.paid_until or datetime.min)
    return latest.paid_until, latest.billing_day or 1


def quote_renewal_price(
    plan: VpsPlan,
    instance: VpsInstance,
    months: int,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
    user=None,
) -> dict:
    if months < 1 or months > MAX_RENEWAL_MONTHS:
        raise HTTPException(
            status_code=400,
            detail=f"Renovação deve ser entre 1 e {MAX_RENEWAL_MONTHS} meses",
        )
    monthly = calculate_monthly_cents(plan, instance, plan_presets=plan_presets)
    subtotal = monthly * months
    discount_percent = renewal_discount_percent(months)
    discount_cents = round(subtotal * discount_percent / 100)
    pending = int(getattr(instance, "admin_pending_charge_cents", 0) or 0)
    if user is not None:
        pending += int(getattr(user, "admin_pending_cloud_charge_cents", 0) or 0)
    total = subtotal - discount_cents + pending
    return {
        "months": months,
        "monthly_cents": monthly,
        "subtotal_cents": subtotal,
        "discount_cents": discount_cents,
        "discount_percent": round(discount_percent, 2),
        "pending_cents": pending,
        "total_cents": total,
    }


def calculate_renewal_price(
    plan: VpsPlan,
    instance: VpsInstance,
    months: int,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
    user=None,
) -> int:
    return quote_renewal_price(
        plan, instance, months, plan_presets=plan_presets, user=user
    )["total_cents"]


def calculate_cloud_renewal_price(user, months: int) -> int:
    if months < 1 or months > MAX_RENEWAL_MONTHS:
        raise HTTPException(
            status_code=400,
            detail=f"Renovação deve ser entre 1 e {MAX_RENEWAL_MONTHS} meses",
        )
    contracted = int(getattr(user, "cloud_contracted_gb", 0) or 0)
    if contracted <= 0:
        raise HTTPException(status_code=400, detail="Nenhum espaço CyberCloud contratado para renovar")
    monthly = int(getattr(user, "cloud_monthly_cents", 0) or 0)
    if monthly <= 0:
        raise HTTPException(status_code=400, detail="Mensalidade CyberCloud não configurada")
    pending = int(getattr(user, "admin_pending_cloud_charge_cents", 0) or 0)
    return monthly * months + pending


def get_cloud_billing_snapshot(user, *, monthly_cents: int | None = None) -> dict:
    now = datetime.utcnow()
    contracted_gb = int(getattr(user, "cloud_contracted_gb", 0) or 0)
    monthly = monthly_cents
    if monthly is None:
        monthly = int(getattr(user, "cloud_monthly_cents", 0) or 0)

    if contracted_gb <= 0 or not user.cloud_paid_until:
        return {
            "billing_state": "none",
            "billing_label": "Sem espaço contratado",
            "paid_until": user.cloud_paid_until,
            "grace_ends_at": None,
            "billing_day": int(getattr(user, "cloud_billing_day", 1) or 1),
            "monthly_cents": monthly if contracted_gb > 0 else 0,
            "contracted_gb": contracted_gb,
            "suspended_for_billing": bool(getattr(user, "cloud_suspended_for_billing", False)),
            "days_until_due": 0,
            "days_in_grace_left": 0,
            "can_upload": True,
        }

    paid_until = user.cloud_paid_until
    grace_ends_at = paid_until + timedelta(days=GRACE_DAYS)

    if bool(getattr(user, "cloud_suspended_for_billing", False)):
        billing_state = "suspended"
        billing_label = "CyberCloud suspenso — renove para reativar o espaço contratado"
    elif now <= paid_until:
        billing_state = "active"
        billing_label = "Em dia"
    elif now <= grace_ends_at:
        billing_state = "grace"
        billing_label = "Vencido — carência de 3 dias"
    else:
        billing_state = "suspended"
        billing_label = "Suspenso — renove para reativar o espaço contratado"

    days_until_due = (paid_until.date() - now.date()).days
    days_in_grace_left = (
        max(0, (grace_ends_at.date() - now.date()).days) if billing_state == "grace" else 0
    )

    return {
        "billing_state": billing_state,
        "billing_label": billing_label,
        "paid_until": paid_until,
        "grace_ends_at": grace_ends_at,
        "billing_day": int(getattr(user, "cloud_billing_day", 1) or 1),
        "monthly_cents": monthly,
        "contracted_gb": contracted_gb,
        "suspended_for_billing": bool(getattr(user, "cloud_suspended_for_billing", False)),
        "days_until_due": days_until_due,
        "days_in_grace_left": days_in_grace_left,
        "can_upload": billing_state != "suspended",
    }


def assert_cloud_billing_allows_upload(user) -> None:
    snapshot = get_cloud_billing_snapshot(user)
    if int(getattr(user, "cloud_contracted_gb", 0) or 0) <= 0:
        return
    if not snapshot["can_upload"]:
        raise HTTPException(
            status_code=402,
            detail=f"Mensalidade CyberCloud vencida há mais de {GRACE_DAYS} dias. "
            "Renove para continuar usando o espaço contratado.",
        )


def quote_web_renewal_price(monthly_cents: int, months: int) -> dict:
    if months < 1 or months > MAX_RENEWAL_MONTHS:
        raise HTTPException(
            status_code=400,
            detail=f"Renovação deve ser entre 1 e {MAX_RENEWAL_MONTHS} meses",
        )
    if monthly_cents <= 0:
        raise HTTPException(status_code=400, detail="Mensalidade do site não configurada")
    subtotal = monthly_cents * months
    discount_percent = renewal_discount_percent(months)
    discount_cents = round(subtotal * discount_percent / 100)
    total = subtotal - discount_cents
    return {
        "months": months,
        "monthly_cents": monthly_cents,
        "subtotal_cents": subtotal,
        "discount_cents": discount_cents,
        "discount_percent": round(discount_percent, 2),
        "total_cents": total,
    }


def get_web_billing_snapshot(site, *, monthly_cents: int | None = None) -> dict:
    now = datetime.utcnow()
    paid_until = site.paid_until or now
    grace_ends_at = paid_until + timedelta(days=GRACE_DAYS)

    if bool(getattr(site, "suspended_for_billing", False)):
        billing_state = "suspended"
        billing_label = "Suspenso — renove para reativar"
    elif now <= paid_until:
        billing_state = "active"
        billing_label = "Em dia"
    elif now <= grace_ends_at:
        billing_state = "grace"
        billing_label = "Vencido — carência de 3 dias"
    else:
        billing_state = "suspended"
        billing_label = "Suspenso — renove para reativar"

    days_until_due = (paid_until.date() - now.date()).days
    days_in_grace_left = (
        max(0, (grace_ends_at.date() - now.date()).days) if billing_state == "grace" else 0
    )

    return {
        "billing_state": billing_state,
        "billing_label": billing_label,
        "paid_until": paid_until,
        "grace_ends_at": grace_ends_at,
        "billing_day": int(getattr(site, "billing_day", 1) or 1),
        "monthly_cents": monthly_cents,
        "suspended_for_billing": bool(getattr(site, "suspended_for_billing", False)),
        "days_until_due": days_until_due,
        "days_in_grace_left": days_in_grace_left,
        "can_power_on": billing_state != "suspended",
    }


def get_billing_snapshot(instance: VpsInstance, *, monthly_cents: int | None = None) -> dict:
    now = datetime.utcnow()
    paid_until = instance.paid_until or now
    grace_ends_at = paid_until + timedelta(days=GRACE_DAYS)

    if now <= paid_until:
        billing_state = "active"
        billing_label = "Em dia"
    elif now <= grace_ends_at:
        billing_state = "grace"
        billing_label = "Vencida — carência de 3 dias"
    else:
        billing_state = "suspended"
        billing_label = "Suspensa — renove para reativar"

    days_until_due = (paid_until.date() - now.date()).days
    days_in_grace_left = max(0, (grace_ends_at.date() - now.date()).days) if billing_state == "grace" else 0

    return {
        "billing_state": billing_state,
        "billing_label": billing_label,
        "paid_until": paid_until,
        "grace_ends_at": grace_ends_at,
        "billing_day": instance.billing_day,
        "monthly_cents": monthly_cents,
        "suspended_for_billing": bool(instance.suspended_for_billing),
        "days_until_due": days_until_due,
        "days_in_grace_left": days_in_grace_left,
        "can_power_on": billing_state != "suspended",
    }


def assert_billing_allows_operations(instance: VpsInstance, *, action: str = "operar") -> None:
    snapshot = get_billing_snapshot(instance)
    if snapshot["billing_state"] == "suspended":
        raise HTTPException(
            status_code=402,
            detail=f"Mensalidade vencida há mais de {GRACE_DAYS} dias. Renove para {action} o servidor.",
        )


def assert_billing_allows_destroy(instance: VpsInstance) -> None:
    snapshot = get_billing_snapshot(instance)
    if snapshot["billing_state"] == "active":
        raise HTTPException(
            status_code=403,
            detail="Remoção disponível apenas após o vencimento da mensalidade.",
        )
