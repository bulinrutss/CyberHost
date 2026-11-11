from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.finance_database import FinanceSessionLocal
from app.models.finance import FinanceEvent, FinanceEventNotice, FinancePushSubscription

logger = logging.getLogger(__name__)

NOTICE_SOON = "soon"
NOTICE_ALL_DAY = "all_day"


def push_public_key() -> str | None:
    settings = get_settings()
    if not settings.finance_push_configured:
        return None
    return settings.vapid_public_key.strip()


def _require_push() -> None:
    if not get_settings().finance_push_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avisos de evento ainda não estão configurados",
        )


def save_subscription(db: Session, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    _require_push()
    endpoint = endpoint.strip()
    p256dh = p256dh.strip()
    auth = auth.strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inscrição inválida")
    if len(endpoint) > 768 or len(p256dh) > 200 or len(auth) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inscrição inválida")
    row = db.query(FinancePushSubscription).filter(FinancePushSubscription.endpoint == endpoint).first()
    if row is None:
        db.add(
            FinancePushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
        )
    elif row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inscrição inválida")
    else:
        row.p256dh = p256dh
        row.auth = auth
    db.commit()


def delete_subscription(db: Session, user_id: int, endpoint: str) -> None:
    row = (
        db.query(FinancePushSubscription)
        .filter(
            FinancePushSubscription.user_id == user_id,
            FinancePushSubscription.endpoint == endpoint.strip(),
        )
        .first()
    )
    if row is None:
        return
    db.delete(row)
    db.commit()


def clear_event_notices(db: Session, event_id: int) -> None:
    db.query(FinanceEventNotice).filter(FinanceEventNotice.event_id == event_id).delete()


def _now_local() -> datetime:
    tz_name = get_settings().finance_timezone or "America/Sao_Paulo"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    return datetime.now(tz).replace(tzinfo=None)


def _due_kind(event: FinanceEvent, now: datetime, lead_minutes: int) -> str | None:
    if event.all_day:
        if event.starts_at.date() != now.date():
            return None
        if now.hour < 8:
            return None
        return NOTICE_ALL_DAY
    fire_at = event.starts_at - timedelta(minutes=max(lead_minutes, 1))
    latest = event.starts_at + timedelta(minutes=2)
    if fire_at <= now <= latest:
        return NOTICE_SOON
    return None


def _payload(event: FinanceEvent) -> dict:
    if event.all_day:
        body = "Compromisso o dia todo"
    else:
        body = f"Começa às {event.starts_at.strftime('%H:%M')}"
    return {
        "title": event.title or "Agenda",
        "body": body,
        "url": "/financeiro",
        "tag": f"finance-event-{event.id}",
    }


def _send_one(sub: FinancePushSubscription, payload: dict) -> bool:
    from app.services import web_push

    return web_push.send(sub.endpoint, sub.p256dh, sub.auth, payload)


def _claim_notice(db: Session, event_id: int, kind: str) -> bool:
    try:
        db.add(FinanceEventNotice(event_id=event_id, kind=kind))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _release_notice(db: Session, event_id: int, kind: str) -> None:
    db.query(FinanceEventNotice).filter(
        FinanceEventNotice.event_id == event_id,
        FinanceEventNotice.kind == kind,
    ).delete()
    db.commit()


def notify_due_events(db: Session | None = None) -> int:
    settings = get_settings()
    if not settings.finance_push_configured:
        return 0
    own = db is None
    if own:
        db = FinanceSessionLocal()
    sent = 0
    try:
        now = _now_local()
        lead = settings.finance_event_lead_minutes
        horizon = now + timedelta(minutes=max(lead, 1) + 5)
        events = (
            db.query(FinanceEvent)
            .filter(FinanceEvent.starts_at <= horizon)
            .filter(FinanceEvent.starts_at >= now - timedelta(hours=16))
            .all()
        )
        for event in events:
            kind = _due_kind(event, now, lead)
            if not kind:
                continue
            subs = (
                db.query(FinancePushSubscription)
                .filter(FinancePushSubscription.user_id == event.user_id)
                .all()
            )
            if not subs:
                continue
            if not _claim_notice(db, event.id, kind):
                continue
            payload = _payload(event)
            delivered = False
            stale: list[FinancePushSubscription] = []
            for sub in subs:
                ok = _send_one(sub, payload)
                if ok:
                    delivered = True
                else:
                    stale.append(sub)
            for sub in stale:
                db.delete(sub)
            if stale:
                db.commit()
            if delivered:
                sent += 1
            else:
                _release_notice(db, event.id, kind)
        return sent
    finally:
        if own:
            db.close()


async def finance_push_loop(interval_seconds: int = 60) -> None:
    while True:
        try:
            sent = await asyncio.to_thread(notify_due_events)
            if sent:
                logger.info("Financeiro: %s aviso(s) de evento enviado(s)", sent)
        except Exception:
            logger.exception("Erro no envio de avisos da agenda")
        await asyncio.sleep(interval_seconds)
