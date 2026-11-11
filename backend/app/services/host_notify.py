"""Avisos do painel: tickets, pedidos, pagamentos e vencimentos."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services import email_templates, host_push

logger = logging.getLogger(__name__)


def on_new_ticket(db: Session, *, ticket_id: int, subject: str, preview: str, customer_user_id: int) -> None:
    host_push.notify_admins(
        db,
        title="Novo ticket de suporte",
        body=f"#{ticket_id} {subject}: {preview}"[:180],
        url="/admin?tab=support",
        tag=f"ticket-{ticket_id}",
        exclude_user_ids={customer_user_id},
    )


def on_ticket_message(
    db: Session,
    *,
    ticket_id: int,
    subject: str,
    preview: str,
    customer_user_id: int,
    author_id: int,
    as_staff: bool,
    assigned_admin_id: int | None,
) -> None:
    body = f"#{ticket_id} {subject}: {preview}"[:180]
    tag = f"ticket-{ticket_id}"
    if as_staff:
        host_push.notify_user(
            db,
            customer_user_id,
            title="Resposta no suporte",
            body=body,
            url="/dashboard/support",
            tag=tag,
            exclude_user_ids={author_id},
        )
        return
    if assigned_admin_id:
        host_push.notify_user(
            db,
            assigned_admin_id,
            title="Cliente respondeu no suporte",
            body=body,
            url="/admin?tab=support",
            tag=tag,
            exclude_user_ids={author_id},
        )
        return
    host_push.notify_admins(
        db,
        title="Cliente respondeu no suporte",
        body=body,
        url="/admin?tab=support",
        tag=tag,
        exclude_user_ids={author_id, customer_user_id},
    )


def on_ticket_mentions(
    db: Session,
    *,
    ticket_id: int,
    subject: str,
    preview: str,
    mentioned_user_ids: list[int],
    author_id: int,
) -> None:
    host_push.notify_users(
        db,
        mentioned_user_ids,
        title="Você foi mencionado no suporte",
        body=f"#{ticket_id} {subject}: {preview}"[:180],
        url="/admin?tab=support",
        tag=f"ticket-mention-{ticket_id}",
        exclude_user_ids={author_id},
    )


def on_ticket_accepted(db: Session, *, ticket_id: int, subject: str, customer_user_id: int, admin_id: int) -> None:
    host_push.notify_user(
        db,
        customer_user_id,
        title="Suporte em atendimento",
        body=f"#{ticket_id} {subject}",
        url="/dashboard/support",
        tag=f"ticket-{ticket_id}",
        exclude_user_ids={admin_id},
    )


def on_ticket_closed(
    db: Session,
    *,
    ticket_id: int,
    subject: str,
    customer_user_id: int,
    actor_id: int,
    actor_is_admin: bool,
    assigned_admin_id: int | None,
) -> None:
    body = f"#{ticket_id} {subject}"
    tag = f"ticket-{ticket_id}"
    if actor_is_admin:
        host_push.notify_user(
            db,
            customer_user_id,
            title="Ticket encerrado",
            body=body,
            url="/dashboard/support",
            tag=tag,
            exclude_user_ids={actor_id},
        )
        return
    if assigned_admin_id:
        host_push.notify_user(
            db,
            assigned_admin_id,
            title="Cliente encerrou o ticket",
            body=body,
            url="/admin?tab=support",
            tag=tag,
            exclude_user_ids={actor_id},
        )
        return
    host_push.notify_admins(
        db,
        title="Cliente encerrou o ticket",
        body=body,
        url="/admin?tab=support",
        tag=tag,
        exclude_user_ids={actor_id, customer_user_id},
    )


def on_new_pending_order(
    db: Session,
    *,
    kind: str,
    summary: str,
    total_cents: int,
    customer_user_id: int,
    admin_url: str = "/admin?tab=accounts",
) -> None:
    price = email_templates.format_brl(total_cents)
    host_push.notify_admins(
        db,
        title=f"Novo pedido {kind}",
        body=f"{summary} — {price}",
        url=admin_url,
        tag=f"order-new-{kind}-{customer_user_id}",
        exclude_user_ids={customer_user_id},
    )


def on_payment_confirmed(
    db: Session,
    *,
    kind: str,
    summary: str,
    total_cents: int,
    customer_user_id: int,
    client_url: str,
    admin_url: str = "/admin?tab=accounts",
) -> None:
    price = email_templates.format_brl(total_cents)
    body = f"{summary} — {price}"
    host_push.notify_user(
        db,
        customer_user_id,
        title="Pagamento confirmado",
        body=body,
        url=client_url,
        tag=f"pay-{kind}-{customer_user_id}",
    )
    host_push.notify_admins(
        db,
        title=f"Pedido {kind} pago",
        body=body,
        url=admin_url,
        tag=f"pay-admin-{kind}-{customer_user_id}",
        exclude_user_ids={customer_user_id},
    )


def on_provision_ready(
    db: Session,
    *,
    kind: str,
    summary: str,
    customer_user_id: int,
    client_url: str,
) -> None:
    host_push.notify_user(
        db,
        customer_user_id,
        title=f"{kind} pronto",
        body=summary,
        url=client_url,
        tag=f"ready-{kind}-{customer_user_id}",
    )


def on_provision_failed(
    db: Session,
    *,
    kind: str,
    summary: str,
    customer_user_id: int,
    client_url: str,
) -> None:
    host_push.notify_user(
        db,
        customer_user_id,
        title=f"Falha ao criar {kind}",
        body=summary,
        url=client_url,
        tag=f"fail-{kind}-{customer_user_id}",
    )
    host_push.notify_admins(
        db,
        title=f"Falha no provisionamento ({kind})",
        body=summary,
        url="/admin?tab=vps",
        tag=f"fail-admin-{kind}-{customer_user_id}",
        exclude_user_ids={customer_user_id},
    )


def on_billing_reminder(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: str,
    url: str,
) -> None:
    host_push.notify_user(
        db,
        user_id,
        title=title,
        body=body,
        url=url,
        tag=f"billing-{user_id}",
    )
