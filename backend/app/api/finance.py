from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.finance_auth import get_current_finance_user
from app.finance_database import get_finance_db
from app.models.finance_user import FinanceUser
from app.schemas.finance import (
    FinanceEventCreate,
    FinanceEventOut,
    FinanceEventUpdate,
    FinanceGoalCreate,
    FinanceGoalDeposit,
    FinanceGoalOut,
    FinanceGoalUpdate,
    FinanceMeta,
    FinancePushSubscribe,
    FinanceStats,
    FinanceTransactionCreate,
    FinanceTransactionOut,
    FinanceTransactionUpdate,
)
from app.services import finance as finance_svc
from app.services import finance_push
from app.services import finance_receipts

router = APIRouter()


@router.get("/meta", response_model=FinanceMeta)
def finance_meta():
    return finance_svc.meta()


@router.get("/stats", response_model=FinanceStats)
def finance_stats(
    months: int = Query(default=6, ge=1, le=24),
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.build_stats(db, user.id, months=months)


@router.get("/transactions", response_model=list[FinanceTransactionOut])
def list_transactions(
    start: date | None = None,
    end: date | None = None,
    kind: str | None = None,
    category: str | None = None,
    payment_method: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.list_transactions(
        db,
        user.id,
        start=start,
        end=end,
        kind=kind,
        category=category,
        payment_method=payment_method,
        limit=limit,
    )


@router.post("/transactions", response_model=FinanceTransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: FinanceTransactionCreate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.create_transaction(db, user.id, payload)


@router.patch("/transactions/{tx_id}", response_model=FinanceTransactionOut)
def update_transaction(
    tx_id: int,
    payload: FinanceTransactionUpdate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_transaction(db, user.id, tx_id)
    return finance_svc.update_transaction(db, row, payload)


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    tx_id: int,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_transaction(db, user.id, tx_id)
    finance_svc.delete_transaction(db, row)


@router.post("/transactions/{tx_id}/receipt", response_model=FinanceTransactionOut)
def upload_receipt(
    tx_id: int,
    file: UploadFile = File(...),
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_transaction(db, user.id, tx_id)
    ext = finance_receipts.save_receipt(row, file)
    row.receipt_ext = ext
    db.commit()
    db.refresh(row)
    return row


@router.get("/transactions/{tx_id}/receipt")
def download_receipt(
    tx_id: int,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_transaction(db, user.id, tx_id)
    path = finance_receipts.open_receipt(row)
    return FileResponse(
        path,
        media_type=finance_receipts.mime_for(row.receipt_ext),
        filename=f"nota-fiscal-{tx_id}.{row.receipt_ext}",
    )


@router.delete("/transactions/{tx_id}/receipt", response_model=FinanceTransactionOut)
def remove_receipt(
    tx_id: int,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_transaction(db, user.id, tx_id)
    finance_receipts.delete_receipt_files(row.user_id, row.id)
    row.receipt_ext = None
    db.commit()
    db.refresh(row)
    return row


@router.get("/events", response_model=list[FinanceEventOut])
def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=300, ge=1, le=500),
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.list_events(db, user.id, start=start, end=end, limit=limit)


@router.post("/events", response_model=FinanceEventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: FinanceEventCreate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.create_event(db, user.id, payload)


@router.patch("/events/{event_id}", response_model=FinanceEventOut)
def update_event(
    event_id: int,
    payload: FinanceEventUpdate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_event(db, user.id, event_id)
    return finance_svc.update_event(db, row, payload)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_event(db, user.id, event_id)
    finance_svc.delete_event(db, row)


@router.get("/goals", response_model=list[FinanceGoalOut])
def list_goals(user: FinanceUser = Depends(get_current_finance_user), db: Session = Depends(get_finance_db)):
    return [finance_svc.serialize_goal(row) for row in finance_svc.list_goals(db, user.id)]


@router.post("/goals", response_model=FinanceGoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: FinanceGoalCreate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    return finance_svc.serialize_goal(finance_svc.create_goal(db, user.id, payload))


@router.patch("/goals/{goal_id}", response_model=FinanceGoalOut)
def update_goal(
    goal_id: int,
    payload: FinanceGoalUpdate,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_goal(db, user.id, goal_id)
    return finance_svc.serialize_goal(finance_svc.update_goal(db, row, payload))


@router.post("/goals/{goal_id}/deposit", response_model=FinanceGoalOut)
def deposit_goal(
    goal_id: int,
    payload: FinanceGoalDeposit,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_goal(db, user.id, goal_id)
    return finance_svc.serialize_goal(finance_svc.deposit_goal(db, row, payload.amount_cents))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    row = finance_svc.get_owned_goal(db, user.id, goal_id)
    finance_svc.delete_goal(db, row)


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe_push(
    payload: FinancePushSubscribe,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    finance_push.save_subscription(
        db, user.id, payload.endpoint, payload.keys.p256dh, payload.keys.auth
    )


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_push(
    payload: FinancePushSubscribe,
    user: FinanceUser = Depends(get_current_finance_user),
    db: Session = Depends(get_finance_db),
):
    finance_push.delete_subscription(db, user.id, payload.endpoint)
