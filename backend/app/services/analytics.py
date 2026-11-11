"""Coleta first-party de acessos e cliques — sem senhas, PIX ou tokens."""

from __future__ import annotations

import hashlib
import logging
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.analytics import AnalyticsEvent
from app.models.user import User
from app.services import auth_throttle

logger = logging.getLogger(__name__)

ALLOWED_DAYS = (7, 30, 90)
ALLOWED_NAMES = frozenset({"page_view", "click", "form_submit", "page_leave"})
ALLOWED_QUERY = frozenset({"tab", "days"})
SECRET_QUERY = frozenset(
    {
        "token",
        "ticket",
        "code",
        "pix",
        "password",
        "secret",
        "brcode",
        "qr",
        "access_token",
        "session",
        "key",
        "otp",
    }
)
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TOP_LIMIT = 12
RECENT_LIMIT = 40
RETAIN_DAYS = 90

_BOT_UA = re.compile(r"bot|crawl|spider|slurp|bingpreview|facebookexternalhit", re.I)


def _clip(value: object, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _id_ok(value: str) -> str:
    raw = _clip(value, 64)
    return raw if ID_RE.match(raw) else ""


def sanitize_path(raw: str, *, fallback: str = "/") -> str:
    text = (raw or "").strip() or fallback
    if "://" in text:
        parsed = urlparse(text)
        path = parsed.path or fallback
        query = parsed.query
    else:
        if "?" in text:
            path, query = text.split("?", 1)
        else:
            path, query = text, ""
    path = path.split("#", 1)[0]
    if not path.startswith("/"):
        path = "/" + path.lstrip("/")
    path = re.sub(r"/{2,}", "/", path)[:200]
    kept: list[str] = []
    for key, values in parse_qs(query, keep_blank_values=False).items():
        low = key.lower()
        if low in SECRET_QUERY:
            continue
        if low not in ALLOWED_QUERY:
            continue
        value = _clip(values[0] if values else "", 24)
        if value:
            kept.append(f"{low}={value}")
    if kept:
        return f"{path}?{'&'.join(sorted(kept))}"
    return path or "/"


def sanitize_referrer(raw: str, request: Request | None = None) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://placeholder.invalid{text}")
    host = (parsed.hostname or "").lower()
    path = sanitize_path(parsed.path or "/")
    origin_host = ""
    if request is not None:
        origin_host = (request.headers.get("host") or "").split(":")[0].lower()
    if host and origin_host and host == origin_host:
        return path[:120]
    if host:
        return host[:120]
    return path[:120]


def parse_ua(ua: str) -> tuple[str, str]:
    text = ua or ""
    browser = "Outro"
    if "Edg/" in text or "Edge/" in text:
        browser = "Edge"
    elif "Chrome/" in text and "Chromium" not in text:
        browser = "Chrome"
    elif "Firefox/" in text:
        browser = "Firefox"
    elif "Safari/" in text and "Chrome/" not in text:
        browser = "Safari"
    elif _BOT_UA.search(text):
        browser = "Bot"
    os_name = "Outro"
    if "Windows" in text:
        os_name = "Windows"
    elif "Android" in text:
        os_name = "Android"
    elif "iPhone" in text or "iPad" in text:
        os_name = "iOS"
    elif "Mac OS" in text or "Macintosh" in text:
        os_name = "macOS"
    elif "Linux" in text:
        os_name = "Linux"
    return browser, os_name


def _ip_hash(ip: str) -> str:
    secret = get_settings().secret_key or "analytics"
    digest = hashlib.sha256(f"{secret}|ip|{ip}".encode("utf-8")).hexdigest()
    return digest[:16]


def _safe_int(value: object, cap: int) -> int:
    try:
        return max(0, min(int(value or 0), cap))
    except (TypeError, ValueError):
        return 0


def _viewport_bucket(width: int) -> str:
    if width <= 0:
        return "desconhecido"
    if width < 640:
        return "mobile"
    if width < 1024:
        return "tablet"
    return "desktop"


def ingest_events(
    db: Session,
    request: Request,
    payload: list[dict[str, Any]],
    user: User | None,
) -> int:
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, auth_throttle.ANALYTICS_IP_SCOPE, ip)
    )
    retry = auth_throttle.add_hit(
        db, auth_throttle.ANALYTICS_IP_SCOPE, ip, ip=ip, failed=False
    )
    auth_throttle.raise_if_limited(retry)

    header_ua = _clip(request.headers.get("user-agent"), 160)
    stored = 0
    hashed = _ip_hash(ip)
    now = datetime.utcnow()
    for item in payload[:20]:
        name = _clip(item.get("name"), 32)
        if name not in ALLOWED_NAMES:
            continue
        path = sanitize_path(str(item.get("path") or "/"))
        ua = _clip(item.get("ua") or header_ua, 160)
        browser, os_name = parse_ua(ua)
        event = AnalyticsEvent(
            name=name,
            path=path,
            label=_clip(item.get("label"), 80),
            target=_clip(item.get("target"), 80),
            href=sanitize_path(str(item.get("href") or ""), fallback=""),
            visitor_id=_id_ok(str(item.get("visitor_id") or "")),
            session_id=_id_ok(str(item.get("session_id") or "")),
            user_id=user.id if user else None,
            is_admin=bool(user and user.is_admin),
            referrer=sanitize_referrer(str(item.get("referrer") or ""), request),
            language=_clip(item.get("language"), 16),
            timezone=_clip(item.get("timezone"), 64),
            ua=ua,
            ua_browser=browser,
            ua_os=os_name,
            viewport_w=_safe_int(item.get("viewport_w"), 16000),
            viewport_h=_safe_int(item.get("viewport_h"), 16000),
            duration_ms=_safe_int(item.get("duration_ms"), 86_400_000),
            scroll_pct=_safe_int(item.get("scroll_pct"), 100),
            ip_hash=hashed,
            created_at=now,
        )
        if event.href == "/":
            event.href = ""
        db.add(event)
        stored += 1
    if stored:
        db.commit()
        if random.random() < 0.02:
            _prune(db)
    return stored


def _prune(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(days=RETAIN_DAYS)
    db.query(AnalyticsEvent).filter(AnalyticsEvent.created_at < cutoff).delete(
        synchronize_session=False
    )
    db.commit()


def _empty_day() -> dict[str, int]:
    return {"page_views": 0, "clicks": 0, "forms": 0, "visitors": 0}


def _entry_events(page_views: list[AnalyticsEvent]) -> list[AnalyticsEvent]:
    first: dict[str, AnalyticsEvent] = {}
    for row in reversed(page_views):
        key = row.session_id or row.visitor_id
        if not key or key in first:
            continue
        first[key] = row
    return list(first.values())


def collect_analytics(db: Session, days: int = 30) -> dict[str, Any]:
    window = days if days in ALLOWED_DAYS else 30
    now = datetime.utcnow()
    since = datetime(now.year, now.month, now.day) - timedelta(days=max(1, window) - 1)
    hour_since = now - timedelta(hours=24)

    rows = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.created_at >= since)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(20000)
        .all()
    )

    page_views = [row for row in rows if row.name == "page_view"]
    clicks = [row for row in rows if row.name == "click"]
    forms = [row for row in rows if row.name == "form_submit"]
    leaves = [row for row in rows if row.name == "page_leave"]

    visitors = {row.visitor_id for row in rows if row.visitor_id}
    sessions = {row.session_id for row in rows if row.session_id}
    users = {row.user_id for row in rows if row.user_id}

    def _count(items: list[AnalyticsEvent], key_fn) -> list[dict[str, Any]]:
        tallies: dict[str, list[str]] = defaultdict(list)
        for item in items:
            key = key_fn(item)
            if not key:
                continue
            tallies[str(key)].append(item.visitor_id or "")
        ranked = sorted(tallies.items(), key=lambda pair: len(pair[1]), reverse=True)
        return [
            {
                "key": key,
                "count": len(ids),
                "unique": len({vid for vid in ids if vid}),
            }
            for key, ids in ranked[:TOP_LIMIT]
        ]

    day_keys = [
        (since.date() + timedelta(days=offset)).isoformat() for offset in range(window)
    ]
    buckets = {key: _empty_day() for key in day_keys}
    visitors_by_day: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.created_at is None:
            continue
        key = row.created_at.date().isoformat()
        if key not in buckets:
            continue
        if row.name == "page_view":
            buckets[key]["page_views"] += 1
        elif row.name == "click":
            buckets[key]["clicks"] += 1
        elif row.name == "form_submit":
            buckets[key]["forms"] += 1
        if row.visitor_id:
            visitors_by_day[key].add(row.visitor_id)
    daily = []
    for key in day_keys:
        bucket = buckets[key]
        daily.append(
            {
                "date": key,
                "page_views": bucket["page_views"],
                "clicks": bucket["clicks"],
                "forms": bucket["forms"],
                "visitors": len(visitors_by_day.get(key, set())),
            }
        )

    hours: dict[str, dict[str, int]] = {}
    cursor = datetime(hour_since.year, hour_since.month, hour_since.day, hour_since.hour)
    while cursor <= now:
        hours[cursor.strftime("%Y-%m-%dT%H:00")] = {"page_views": 0, "clicks": 0}
        cursor += timedelta(hours=1)
    for row in rows:
        if row.created_at is None or row.created_at < hour_since:
            continue
        key = row.created_at.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
        if key not in hours:
            continue
        if row.name == "page_view":
            hours[key]["page_views"] += 1
        elif row.name == "click":
            hours[key]["clicks"] += 1
    hourly = [{"hour": key, **value} for key, value in hours.items()]

    user_names: dict[int, str] = {}
    if users:
        for person in db.query(User).filter(User.id.in_(list(users))).all():
            user_names[person.id] = person.name

    durations = [row.duration_ms for row in leaves if row.duration_ms > 0]
    scrolls = [row.scroll_pct for row in leaves if row.scroll_pct > 0]
    avg_duration = int(sum(durations) / len(durations)) if durations else 0
    avg_scroll = int(sum(scrolls) / len(scrolls)) if scrolls else 0

    recent = []
    for row in rows[:RECENT_LIMIT]:
        recent.append(
            {
                "at": row.created_at,
                "name": row.name,
                "path": row.path,
                "label": row.label,
                "user_name": user_names.get(row.user_id) if row.user_id else None,
                "is_admin": bool(row.is_admin),
            }
        )

    return {
        "days": window,
        "generated_at": now,
        "totals": {
            "page_views": len(page_views),
            "clicks": len(clicks),
            "forms": len(forms),
            "page_leaves": len(leaves),
            "unique_visitors": len(visitors),
            "unique_sessions": len(sessions),
            "identified_users": len(users),
            "avg_duration_ms": avg_duration,
            "avg_scroll_pct": avg_scroll,
        },
        "auth": {
            "anonymous": sum(1 for row in page_views if not row.user_id),
            "logged_in": sum(1 for row in page_views if row.user_id and not row.is_admin),
            "admin": sum(1 for row in page_views if row.is_admin),
        },
        "daily": daily,
        "hourly": hourly,
        "top_pages": _count(page_views, lambda row: row.path),
        "top_clicks": _count(clicks, lambda row: row.label or row.target or "(sem rótulo)"),
        "top_forms": _count(forms, lambda row: row.label or row.path),
        "top_entry": _count(_entry_events(page_views), lambda row: row.path),
        "browsers": _count(page_views, lambda row: row.ua_browser or "Outro"),
        "systems": _count(page_views, lambda row: row.ua_os or "Outro"),
        "languages": _count(page_views, lambda row: row.language or "desconhecido"),
        "referrers": _count(page_views, lambda row: row.referrer or "(direto)"),
        "viewports": _count(page_views, lambda row: _viewport_bucket(row.viewport_w)),
        "recent": recent,
    }


def require_collect_payload(events: list[Any]) -> list[dict[str, Any]]:
    if not events:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum evento")
    return [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in events]
