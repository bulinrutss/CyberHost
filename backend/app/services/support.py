"""Tickets de suporte: chat com o cliente, aceite e menções entre admins."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.support import (
    TICKET_ACCEPTED,
    TICKET_CLOSED,
    TICKET_OPEN,
    SupportMention,
    SupportMessage,
    SupportTicket,
)
from app.models.user import User
from app.schemas.support import (
    SupportMessageOut,
    SupportStaffItem,
    SupportTicketDetail,
    SupportTicketListItem,
)
from app.services import email_templates, host_notify, mailer

logger = logging.getLogger(__name__)

MAX_OPEN_TICKETS = 8
MAX_TICKETS_PER_DAY = 10
MAX_MESSAGES_PER_WINDOW = 40
MESSAGE_WINDOW = timedelta(minutes=10)
PREVIEW_LEN = 140
WELCOME = "Recebemos seu pedido de suporte. A equipe responde o mais breve possível."
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str, *, max_len: int, field: str = "texto") -> str:
    text = _CONTROL.sub("", value or "")
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = "\n".join(lines).strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Informe o {field}")
    if len(text) > max_len:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field.capitalize()} muito longo",
        )
    return text


def _preview(text: str) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= PREVIEW_LEN:
        return compact
    return compact[: PREVIEW_LEN - 1] + "…"


def _users_by_id(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {row.id: row for row in rows}


def _staff_name(user: User | None) -> str:
    if user is None:
        return "Equipe"
    name = (user.name or "").strip()
    return name or "Equipe"


def active_staff(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.is_admin.is_(True), User.is_active.is_(True))
        .order_by(User.name.asc())
        .all()
    )


def staff_directory(db: Session) -> list[SupportStaffItem]:
    return [SupportStaffItem(id=user.id, name=_staff_name(user)) for user in active_staff(db)]


def _safe_send_email(*, to_email: str, subject: str, text: str, html: str) -> None:
    if not mailer.smtp_configured():
        logger.info("support email skipped: smtp not configured")
        return
    try:
        mailer.send_email(to_email=to_email, subject=subject, text=text, html=html)
    except Exception:
        logger.warning("support email failed")


def notify_new_ticket(db: Session, ticket: SupportTicket, body: str) -> None:
    customer = db.get(User, ticket.user_id)
    customer_name = _staff_name(customer) if customer else "Cliente"
    preview = _preview(body)
    logo = mailer.logo_src(inline=bool(mailer.load_logo_bytes()))
    cta = mailer.panel_url("/admin?tab=support")
    for admin in active_staff(db):
        email = (admin.email or "").strip()
        if not email or admin.id == ticket.user_id:
            continue
        subject, text, html = email_templates.support_new_ticket_content(
            admin_name=_staff_name(admin),
            customer_name=customer_name,
            ticket_id=ticket.id,
            ticket_subject=ticket.subject,
            preview=preview,
            cta_url=cta,
            logo_src=logo,
        )
        _safe_send_email(to_email=email, subject=subject, text=text, html=html)


def notify_mentions(
    db: Session,
    *,
    ticket: SupportTicket,
    from_user: User,
    mentioned: list[User],
    body: str,
) -> None:
    preview = _preview(body)
    logo = mailer.logo_src(inline=bool(mailer.load_logo_bytes()))
    cta = mailer.panel_url("/admin?tab=support")
    from_name = _staff_name(from_user)
    for admin in mentioned:
        email = (admin.email or "").strip()
        if not email:
            continue
        subject, text, html = email_templates.support_mention_content(
            admin_name=_staff_name(admin),
            from_name=from_name,
            ticket_id=ticket.id,
            ticket_subject=ticket.subject,
            preview=preview,
            cta_url=cta,
            logo_src=logo,
        )
        _safe_send_email(to_email=email, subject=subject, text=text, html=html)


def notify_ticket_accepted(db: Session, ticket: SupportTicket, admin: User) -> None:
    customer = db.get(User, ticket.user_id)
    if customer is None:
        return
    email = (customer.email or "").strip()
    if not email:
        return
    logo = mailer.logo_src(inline=bool(mailer.load_logo_bytes()))
    cta = mailer.panel_url("/dashboard/support")
    subject, text, html = email_templates.support_ticket_accepted_content(
        customer_name=_staff_name(customer),
        admin_name=_staff_name(admin),
        ticket_id=ticket.id,
        ticket_subject=ticket.subject,
        cta_url=cta,
        logo_src=logo,
    )
    _safe_send_email(to_email=email, subject=subject, text=text, html=html)


def _append_message(
    db: Session,
    ticket: SupportTicket,
    *,
    author: User | None,
    body: str,
    is_system: bool = False,
) -> SupportMessage:
    now = datetime.utcnow()
    message = SupportMessage(
        ticket_id=ticket.id,
        author_id=None if author is None else author.id,
        body=body,
        is_system=is_system,
        created_at=now,
    )
    db.add(message)
    ticket.last_message_preview = _preview(body)
    ticket.last_message_at = now
    ticket.updated_at = now
    db.flush()
    return message


def _count_open(db: Session, user_id: int) -> int:
    return (
        db.query(SupportTicket)
        .filter(
            SupportTicket.user_id == user_id,
            SupportTicket.status.in_((TICKET_OPEN, TICKET_ACCEPTED)),
        )
        .count()
    )


def _count_created_today(db: Session, user_id: int) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user_id, SupportTicket.created_at >= since)
        .count()
    )


def _count_recent_messages(db: Session, author_id: int) -> int:
    since = datetime.utcnow() - MESSAGE_WINDOW
    return (
        db.query(SupportMessage)
        .filter(
            SupportMessage.author_id == author_id,
            SupportMessage.is_system.is_(False),
            SupportMessage.created_at >= since,
        )
        .count()
    )


def create_ticket(db: Session, user: User, subject: str, body: str) -> SupportTicket:
    subject = clean_text(subject, max_len=80, field="assunto")
    body = clean_text(body, max_len=4000, field="motivo")
    if _count_open(db, user.id) >= MAX_OPEN_TICKETS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Você já tem tickets em aberto. Aguarde a resposta ou encerre um ticket.",
        )
    if _count_created_today(db, user.id) >= MAX_TICKETS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite diário de tickets atingido. Tente de novo amanhã.",
        )
    now = datetime.utcnow()
    ticket = SupportTicket(
        user_id=user.id,
        subject=subject,
        status=TICKET_OPEN,
        last_message_preview=_preview(body),
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    _append_message(db, ticket, author=user, body=body)
    _append_message(db, ticket, author=None, body=WELCOME, is_system=True)
    db.commit()
    db.refresh(ticket)
    notify_new_ticket(db, ticket, body)
    host_notify.on_new_ticket(
        db,
        ticket_id=ticket.id,
        subject=ticket.subject,
        preview=_preview(body),
        customer_user_id=ticket.user_id,
    )
    return ticket


def add_message(
    db: Session,
    ticket: SupportTicket,
    author: User,
    body: str,
    *,
    mention_ids: list[int] | None = None,
    as_staff: bool,
) -> SupportMessage:
    if ticket.status == TICKET_CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este ticket já foi encerrado",
        )
    body = clean_text(body, max_len=4000, field="mensagem")
    if _count_recent_messages(db, author.id) >= MAX_MESSAGES_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas mensagens em pouco tempo. Aguarde um instante.",
        )
    mentioned_users: list[User] = []
    if as_staff and mention_ids:
        mentioned_users = _resolve_mentions(db, author, mention_ids)
    message = _append_message(db, ticket, author=author, body=body)
    for mentioned in mentioned_users:
        db.add(
            SupportMention(
                message_id=message.id,
                ticket_id=ticket.id,
                mentioned_user_id=mentioned.id,
            )
        )
    db.commit()
    db.refresh(message)
    if mentioned_users:
        notify_mentions(
            db,
            ticket=ticket,
            from_user=author,
            mentioned=mentioned_users,
            body=body,
        )
        host_notify.on_ticket_mentions(
            db,
            ticket_id=ticket.id,
            subject=ticket.subject,
            preview=_preview(body),
            mentioned_user_ids=[row.id for row in mentioned_users],
            author_id=author.id,
        )
    host_notify.on_ticket_message(
        db,
        ticket_id=ticket.id,
        subject=ticket.subject,
        preview=_preview(body),
        customer_user_id=ticket.user_id,
        author_id=author.id,
        as_staff=as_staff,
        assigned_admin_id=ticket.accepted_by_id,
    )
    return message


def _resolve_mentions(db: Session, author: User, mention_ids: list[int]) -> list[User]:
    unique: list[int] = []
    seen: set[int] = set()
    for raw in mention_ids:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid <= 0 or uid == author.id or uid in seen:
            continue
        seen.add(uid)
        unique.append(uid)
        if len(unique) >= 20:
            break
    if not unique:
        return []
    rows = (
        db.query(User)
        .filter(User.id.in_(unique), User.is_admin.is_(True), User.is_active.is_(True))
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[uid] for uid in unique if uid in by_id]


def accept_ticket(db: Session, ticket: SupportTicket, admin: User) -> SupportTicket:
    if ticket.status == TICKET_CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este ticket já foi encerrado",
        )
    previous = db.get(User, ticket.accepted_by_id) if ticket.accepted_by_id else None
    ticket.status = TICKET_ACCEPTED
    ticket.accepted_by_id = admin.id
    ticket.updated_at = datetime.utcnow()
    changed = previous is None or previous.id != admin.id
    if previous is None:
        note = f"{_staff_name(admin)} aceitou o atendimento."
    elif previous.id == admin.id:
        note = f"{_staff_name(admin)} continua no atendimento."
    else:
        note = f"{_staff_name(admin)} assumiu o atendimento no lugar de {_staff_name(previous)}."
    if changed:
        _append_message(db, ticket, author=admin, body=note, is_system=True)
    db.commit()
    db.refresh(ticket)
    if changed:
        notify_ticket_accepted(db, ticket, admin)
        host_notify.on_ticket_accepted(
            db,
            ticket_id=ticket.id,
            subject=ticket.subject,
            customer_user_id=ticket.user_id,
            admin_id=admin.id,
        )
    return ticket


def close_ticket(db: Session, ticket: SupportTicket, actor: User) -> SupportTicket:
    if ticket.status == TICKET_CLOSED:
        return ticket
    ticket.status = TICKET_CLOSED
    ticket.updated_at = datetime.utcnow()
    who = "cliente" if not actor.is_admin else _staff_name(actor)
    if actor.is_admin:
        note = f"Ticket encerrado por {who}."
    else:
        note = "Ticket encerrado pelo cliente."
    _append_message(db, ticket, author=actor, body=note, is_system=True)
    db.commit()
    db.refresh(ticket)
    host_notify.on_ticket_closed(
        db,
        ticket_id=ticket.id,
        subject=ticket.subject,
        customer_user_id=ticket.user_id,
        actor_id=actor.id,
        actor_is_admin=bool(actor.is_admin),
        assigned_admin_id=ticket.accepted_by_id,
    )
    return ticket


def delete_ticket(db: Session, ticket: SupportTicket) -> None:
    ticket_id = ticket.id
    db.query(SupportMention).filter(SupportMention.ticket_id == ticket_id).delete(
        synchronize_session=False
    )
    db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket_id).delete(
        synchronize_session=False
    )
    db.delete(ticket)
    db.commit()
    logger.info("Admin apagou ticket id=%s", ticket_id)


def get_owned_ticket(db: Session, ticket_id: int, user: User) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket não encontrado")
    if ticket.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket não encontrado")
    return ticket


def get_any_ticket(db: Session, ticket_id: int) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket não encontrado")
    return ticket


def list_customer_tickets(db: Session, user_id: int) -> list[SupportTicket]:
    return (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.last_message_at.desc())
        .limit(100)
        .all()
    )


def list_admin_tickets(db: Session, *, include_closed: bool) -> list[SupportTicket]:
    query = db.query(SupportTicket)
    if not include_closed:
        query = query.filter(SupportTicket.status.in_((TICKET_OPEN, TICKET_ACCEPTED)))
    return query.order_by(SupportTicket.last_message_at.desc()).limit(200).all()


def _waiting_on_staff(ticket: SupportTicket, last_author: User | None) -> bool:
    if ticket.status == TICKET_CLOSED:
        return False
    if last_author is None:
        return True
    return not last_author.is_admin


def serialize_list_item(
    ticket: SupportTicket,
    users: dict[int, User],
    *,
    last_author: User | None = None,
) -> SupportTicketListItem:
    owner = users.get(ticket.user_id)
    accepted = users.get(ticket.accepted_by_id) if ticket.accepted_by_id else None
    return SupportTicketListItem(
        id=ticket.id,
        subject=ticket.subject,
        status=ticket.status,
        user_id=ticket.user_id,
        user_name=_staff_name(owner) if owner else "Cliente",
        accepted_by_id=ticket.accepted_by_id,
        accepted_by_name=_staff_name(accepted) if accepted else None,
        last_message_preview=ticket.last_message_preview or "",
        last_message_at=ticket.last_message_at,
        created_at=ticket.created_at,
        waiting_on_staff=_waiting_on_staff(ticket, last_author),
    )


def _last_human_author(db: Session, ticket_ids: list[int]) -> dict[int, int]:
    if not ticket_ids:
        return {}
    rows = (
        db.query(SupportMessage.ticket_id, SupportMessage.author_id, SupportMessage.id)
        .filter(
            SupportMessage.ticket_id.in_(ticket_ids),
            SupportMessage.is_system.is_(False),
            SupportMessage.author_id.isnot(None),
        )
        .order_by(SupportMessage.id.desc())
        .all()
    )
    latest: dict[int, int] = {}
    for ticket_id, author_id, _message_id in rows:
        if ticket_id not in latest and author_id is not None:
            latest[ticket_id] = int(author_id)
    return latest


def serialize_tickets(db: Session, tickets: list[SupportTicket]) -> list[SupportTicketListItem]:
    ids = {ticket.user_id for ticket in tickets}
    ids.update(ticket.accepted_by_id for ticket in tickets if ticket.accepted_by_id)
    last_authors = _last_human_author(db, [ticket.id for ticket in tickets])
    ids.update(last_authors.values())
    users = _users_by_id(db, ids)
    return [
        serialize_list_item(
            ticket,
            users,
            last_author=users.get(last_authors[ticket.id]) if ticket.id in last_authors else None,
        )
        for ticket in tickets
    ]


def serialize_detail(db: Session, ticket: SupportTicket) -> SupportTicketDetail:
    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.id.asc())
        .limit(500)
        .all()
    )
    mention_map: dict[int, list[int]] = {}
    if messages:
        mentions = (
            db.query(SupportMention)
            .filter(SupportMention.message_id.in_([item.id for item in messages]))
            .all()
        )
        for row in mentions:
            mention_map.setdefault(row.message_id, []).append(row.mentioned_user_id)
    user_ids = {ticket.user_id}
    if ticket.accepted_by_id:
        user_ids.add(ticket.accepted_by_id)
    for message in messages:
        if message.author_id:
            user_ids.add(message.author_id)
    users = _users_by_id(db, user_ids)
    last_human = None
    for message in reversed(messages):
        if not message.is_system and message.author_id:
            last_human = users.get(message.author_id)
            break
    base = serialize_list_item(ticket, users, last_author=last_human)
    out_messages: list[SupportMessageOut] = []
    for message in messages:
        author = users.get(message.author_id) if message.author_id else None
        out_messages.append(
            SupportMessageOut(
                id=message.id,
                author_id=message.author_id,
                author_name="CyberHost" if message.is_system and author is None else _staff_name(author),
                author_is_admin=bool(author and author.is_admin),
                body=message.body,
                is_system=message.is_system,
                mentioned_user_ids=mention_map.get(message.id, []),
                created_at=message.created_at,
            )
        )
    return SupportTicketDetail(**base.model_dump(), messages=out_messages)
