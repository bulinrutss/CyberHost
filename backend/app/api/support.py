"""Tickets de suporte do cliente."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.support import (
    SupportMessageCreate,
    SupportTicketCreate,
    SupportTicketDetail,
    SupportTicketListItem,
)
from app.services import support as support_svc

router = APIRouter()


@router.get("/tickets", response_model=list[SupportTicketListItem])
def list_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use o painel administrativo para o suporte",
        )
    tickets = support_svc.list_customer_tickets(db, user.id)
    return support_svc.serialize_tickets(db, tickets)


@router.post("/tickets", response_model=SupportTicketDetail, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: SupportTicketCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use o painel administrativo para o suporte",
        )
    ticket = support_svc.create_ticket(db, user, payload.subject, payload.body)
    return support_svc.serialize_detail(db, ticket)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetail)
def get_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_owned_ticket(db, ticket_id, user)
    return support_svc.serialize_detail(db, ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetail)
def send_message(
    ticket_id: int,
    payload: SupportMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_owned_ticket(db, ticket_id, user)
    support_svc.add_message(
        db,
        ticket,
        user,
        payload.body,
        mention_ids=[],
        as_staff=False,
    )
    return support_svc.serialize_detail(db, ticket)


@router.post("/tickets/{ticket_id}/close", response_model=SupportTicketDetail)
def close_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_svc.get_owned_ticket(db, ticket_id, user)
    support_svc.close_ticket(db, ticket, user)
    return support_svc.serialize_detail(db, ticket)
