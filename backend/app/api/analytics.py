"""Coleta anônima/autenticada de eventos de uso do painel."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import get_optional_user
from app.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsCollectRequest
from app.services import analytics as analytics_svc

router = APIRouter()


@router.post("/collect")
def collect_analytics(
    payload: AnalyticsCollectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    events = analytics_svc.require_collect_payload(payload.events)
    stored = analytics_svc.ingest_events(db, request, events, user)
    return {"stored": stored}
