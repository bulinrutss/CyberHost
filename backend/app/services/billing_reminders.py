"""Lembretes de vencimento VPS e CyberCloud por e-mail."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.billing_reminder import BillingReminder
from app.models.user import User
from app.models.vps import VpsInstance, VpsStatus
from app.services import email_templates, mailer
from app.services.billing import calculate_monthly_cents, get_billing_snapshot, get_cloud_billing_snapshot
from app.services.plan_presets import list_plan_presets

logger = logging.getLogger(__name__)

KIND_VPS = "vps"
KIND_CLOUD = "cloud"
BEFORE_OFFSETS = (10, 5, 3, 2, 1)
AFTER_OFFSETS = (-1, -2, -3, -4, -5)
ACTIVE_OFFSETS = set(BEFORE_OFFSETS) | set(AFTER_OFFSETS)


def reminder_offset(days_until_due: int) -> int | None:
    if days_until_due in ACTIVE_OFFSETS:
        return days_until_due
    return None


def _already_sent(db: Session, kind: str, resource_id: int, due_on, offset_days: int) -> bool:
    row = (
        db.query(BillingReminder)
        .filter(
            BillingReminder.kind == kind,
            BillingReminder.resource_id == resource_id,
            BillingReminder.due_on == due_on,
            BillingReminder.offset_days == offset_days,
        )
        .first()
    )
    return row is not None


def _mark_sent(db: Session, kind: str, resource_id: int, user_id: int, due_on, offset_days: int) -> bool:
    db.add(
        BillingReminder(
            kind=kind,
            resource_id=resource_id,
            user_id=user_id,
            due_on=due_on,
            offset_days=offset_days,
            sent_at=datetime.utcnow(),
        )
    )
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _badge(offset: int) -> str:
    if offset < 0:
        n = abs(offset)
        return f"Vencido há {n} dia(s)"
    if offset == 1:
        return "Vence amanhã"
    return f"Vence em {offset} dias"


def _due_label(paid_until: datetime, offset: int) -> str:
    when = paid_until.strftime("%d/%m/%Y")
    if offset < 0:
        return f"Venceu em {when}"
    return f"Vence em {when}"


def collect_due_items(db: Session, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.utcnow()
    items: list[dict] = []

    instances = (
        db.query(VpsInstance)
        .filter(
            VpsInstance.status != VpsStatus.DELETED,
            VpsInstance.paid_until.isnot(None),
        )
        .all()
    )
    users_by_id: dict[int, User] = {}

    def user_of(user_id: int) -> User | None:
        if user_id not in users_by_id:
            users_by_id[user_id] = db.get(User, user_id)
        return users_by_id[user_id]

    for instance in instances:
        user = user_of(instance.user_id)
        email = (getattr(user, "email", None) or "").strip() if user else ""
        if not user or not email or "@" not in email:
            continue
        days_until_due = (instance.paid_until.date() - now.date()).days
        offset = reminder_offset(days_until_due)
        if offset is None:
            continue
        due_on = instance.paid_until.date()
        if _already_sent(db, KIND_VPS, instance.id, due_on, offset):
            continue
        snapshot = get_billing_snapshot(instance)
        monthly = snapshot.get("monthly_cents")
        if monthly is None:
            try:
                from app.models.vps import VpsPlan

                plan = db.get(VpsPlan, instance.plan_id) if instance.plan_id else None
                presets = list_plan_presets(db, plan.id) if plan else []
                monthly = calculate_monthly_cents(plan, instance, plan_presets=presets)
            except Exception:
                monthly = None
        items.append(
            {
                "kind": KIND_VPS,
                "resource_id": instance.id,
                "user_id": user.id,
                "email": email,
                "name": user.name or "",
                "due_on": due_on,
                "offset_days": offset,
                "overdue": offset < 0,
                "title": instance.vm_name or f"VPS #{instance.id}",
                "detail": f"{instance.vcpu} vCPU · {(instance.ram_mb or 0) // 1024} GB RAM · {instance.disk_gb} GB",
                "due_label": _due_label(instance.paid_until, offset),
                "price_label": email_templates.format_brl(monthly),
                "badge": _badge(offset),
                "cta_path": f"/dashboard/vps/{instance.id}",
            }
        )

    cloud_users = (
        db.query(User)
        .filter(
            User.cloud_contracted_gb > 0,
            User.cloud_paid_until.isnot(None),
            User.email.isnot(None),
        )
        .all()
    )
    for user in cloud_users:
        email = (user.email or "").strip()
        if not email or "@" not in email:
            continue
        days_until_due = (user.cloud_paid_until.date() - now.date()).days
        offset = reminder_offset(days_until_due)
        if offset is None:
            continue
        due_on = user.cloud_paid_until.date()
        if _already_sent(db, KIND_CLOUD, user.id, due_on, offset):
            continue
        snapshot = get_cloud_billing_snapshot(user)
        if snapshot.get("billing_state") == "none":
            continue
        gb = int(snapshot.get("contracted_gb") or user.cloud_contracted_gb or 0)
        items.append(
            {
                "kind": KIND_CLOUD,
                "resource_id": user.id,
                "user_id": user.id,
                "email": email,
                "name": user.name or "",
                "due_on": due_on,
                "offset_days": offset,
                "overdue": offset < 0,
                "title": "CyberCloud",
                "detail": f"{gb} GB contratados",
                "due_label": _due_label(user.cloud_paid_until, offset),
                "price_label": email_templates.format_brl(snapshot.get("monthly_cents")),
                "badge": _badge(offset),
                "cta_path": "/dashboard/files",
            }
        )

    return items


def send_due_reminders(db: Session | None = None, *, now: datetime | None = None) -> int:
    settings = get_settings()
    if not bool(getattr(settings, "billing_reminder_enabled", True)):
        return 0
    if not mailer.smtp_configured(settings):
        return 0

    from app.database import SessionLocal

    own_session = db is None
    session = db or SessionLocal()
    sent = 0
    try:
        items = collect_due_items(session, now=now)
        grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for item in items:
            grouped[(item["user_id"], item["email"])].append(item)

        logo = mailer.load_logo_bytes()
        src = mailer.logo_src(inline=bool(logo))

        for (user_id, email), group in grouped.items():
            group.sort(key=lambda row: row["offset_days"])
            urgent = min(row["offset_days"] for row in group)
            cta = mailer.panel_url(group[0]["cta_path"])
            if len({row["cta_path"] for row in group}) > 1:
                cta = mailer.panel_url("/dashboard")
            subject, text, html = email_templates.billing_content(
                name=group[0]["name"],
                items=group,
                cta_url=cta,
                logo_src=src,
                most_urgent_days=urgent,
            )
            try:
                mailer.send_email(
                    to_email=email,
                    subject=subject,
                    text=text,
                    html=html,
                    inline_logo=True,
                )
            except Exception:
                logger.warning("billing reminder failed user_id=%s", user_id)
                continue
            marked = 0
            for row in group:
                if _mark_sent(
                    session,
                    row["kind"],
                    row["resource_id"],
                    row["user_id"],
                    row["due_on"],
                    row["offset_days"],
                ):
                    marked += 1
            if marked:
                sent += 1
                from app.services import host_notify

                titles = [row.get("title") or "serviço" for row in group]
                unique_titles = list(dict.fromkeys(titles))
                summary = ", ".join(unique_titles[:3])
                if urgent < 0:
                    push_title = "Vencimento em atraso"
                    push_body = f"{summary} — {abs(urgent)} dia(s) em atraso"
                elif urgent == 0:
                    push_title = "Vence hoje"
                    push_body = summary
                else:
                    push_title = "Vencimento próximo"
                    push_body = f"{summary} — falta {urgent} dia(s)"
                host_notify.on_billing_reminder(
                    session,
                    user_id=user_id,
                    title=push_title,
                    body=push_body,
                    url=group[0].get("cta_path") or "/dashboard",
                )
                logger.info(
                    "billing reminder sent user_id=%s items=%s offset=%s",
                    user_id,
                    marked,
                    urgent,
                )
        return sent
    finally:
        if own_session:
            session.close()
