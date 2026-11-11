"""Inscrições Web Push do painel CyberHost (cliente e admin)."""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.host_push import HostPushSubscription
from app.models.user import User
from app.services import web_push

logger = logging.getLogger(__name__)


def push_public_key() -> str | None:
    return web_push.public_key()


def _require_push() -> None:
    if not web_push.configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avisos no celular ainda não estão configurados",
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
    row = db.query(HostPushSubscription).filter(HostPushSubscription.endpoint == endpoint).first()
    if row is None:
        db.add(HostPushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth))
    elif row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inscrição inválida")
    else:
        row.p256dh = p256dh
        row.auth = auth
    db.commit()


def delete_subscription(db: Session, user_id: int, endpoint: str) -> None:
    row = (
        db.query(HostPushSubscription)
        .filter(
            HostPushSubscription.user_id == user_id,
            HostPushSubscription.endpoint == endpoint.strip(),
        )
        .first()
    )
    if row is None:
        return
    db.delete(row)
    db.commit()


def _payload(title: str, body: str, url: str, tag: str) -> dict:
    return {
        "title": (title or "CyberHost")[:80],
        "body": (body or "")[:180],
        "url": url or "/dashboard",
        "tag": (tag or "cyberhost")[:64],
    }


def _deliver(db: Session, subs: list[HostPushSubscription], payload: dict) -> int:
    sent = 0
    stale: list[HostPushSubscription] = []
    for sub in subs:
        ok = web_push.send(sub.endpoint, sub.p256dh, sub.auth, payload)
        if ok:
            sent += 1
        else:
            stale.append(sub)
    for sub in stale:
        db.delete(sub)
    if stale:
        db.commit()
    return sent


def notify_user(
    db: Session,
    user_id: int,
    *,
    title: str,
    body: str,
    url: str = "/dashboard",
    tag: str = "cyberhost",
    exclude_user_ids: set[int] | None = None,
) -> int:
    try:
        if not web_push.configured():
            return 0
        if exclude_user_ids and user_id in exclude_user_ids:
            return 0
        subs = (
            db.query(HostPushSubscription)
            .filter(HostPushSubscription.user_id == user_id)
            .all()
        )
        if not subs:
            return 0
        return _deliver(db, subs, _payload(title, body, url, tag))
    except Exception:
        logger.exception("host push notify_user failed")
        return 0


def notify_users(
    db: Session,
    user_ids: list[int] | set[int],
    *,
    title: str,
    body: str,
    url: str,
    tag: str,
    exclude_user_ids: set[int] | None = None,
) -> int:
    sent = 0
    seen: set[int] = set()
    skip = exclude_user_ids or set()
    for uid in user_ids:
        if uid in seen or uid in skip:
            continue
        seen.add(uid)
        sent += notify_user(
            db, uid, title=title, body=body, url=url, tag=tag
        )
    return sent


def notify_admins(
    db: Session,
    *,
    title: str,
    body: str,
    url: str = "/admin",
    tag: str = "cyberhost-admin",
    exclude_user_ids: set[int] | None = None,
) -> int:
    try:
        if not web_push.configured():
            return 0
        skip = exclude_user_ids or set()
        admins = (
            db.query(User)
            .filter(User.is_admin.is_(True), User.is_active.is_(True))
            .all()
        )
        ids = [row.id for row in admins if row.id not in skip]
        return notify_users(db, ids, title=title, body=body, url=url, tag=tag)
    except Exception:
        logger.exception("host push notify_admins failed")
        return 0
