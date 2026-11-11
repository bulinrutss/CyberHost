"""Atendimento de tickets de suporte (administradores)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.support import (
    SupportMessageCreate,
    SupportStaffItem,
    SupportTicketDetail,
    SupportTicketListItem,
)
from app.services import support as support_svc

router = APIRouter()


@router.get("/tickets", response_model=list[SupportTicketListItem])
def list_tickets(
    include_closed: bool = Query(default=False),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    tickets = support_svc.list_admin_tickets(db, include_closed=include_closed)
    return support_svc.serialize_tickets(db, tickets)


@router.get("/staff", response_model=list[SupportStaffItem])
def list_staff(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return support_svc.staff_directory(db)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetail)
def get_ticket(
    ticket_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_any_ticket(db, ticket_id)
    return support_svc.serialize_detail(db, ticket)


@router.post("/tickets/{ticket_id}/accept", response_model=SupportTicketDetail)
def accept_ticket(
    ticket_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_any_ticket(db, ticket_id)
    support_svc.accept_ticket(db, ticket, admin)
    return support_svc.serialize_detail(db, ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetail)
def send_message(
    ticket_id: int,
    payload: SupportMessageCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_any_ticket(db, ticket_id)
    support_svc.add_message(
        db,
        ticket,
        admin,
        payload.body,
        mention_ids=payload.mention_ids,
        as_staff=True,
    )
    return support_svc.serialize_detail(db, ticket)


@router.post("/tickets/{ticket_id}/close", response_model=SupportTicketDetail)
def close_ticket(
    ticket_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_any_ticket(db, ticket_id)
    support_svc.close_ticket(db, ticket, admin)
    return support_svc.serialize_detail(db, ticket)


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_any_ticket(db, ticket_id)
    support_svc.delete_ticket(db, ticket)
