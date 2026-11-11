"""Estatísticas de visualizações e cliques das páginas publicadas."""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.web_site import WebSite, WebSiteStatus
from app.models.web_site_analytics import WebSiteAnalyticsEvent
from app.schemas.web_page import WebPageLink
from app.services import auth_throttle
from app.services.analytics import _BOT_UA
from app.services.web_page_builder import load_config
from app.services.web_slug import normalize_slug

logger = logging.getLogger(__name__)

ALLOWED_DAYS = (7, 30, 90)
VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
WEB_ANALYTICS_SCOPE = auth_throttle.WEB_ANALYTICS_IP_SCOPE


def _clip(value: object, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _visitor_key(raw: str, ip: str) -> str:
    visitor = _clip(raw, 64)
    if visitor and VISITOR_RE.match(visitor):
        return visitor[:64]
    secret = get_settings().secret_key or "web-analytics"
    digest = hashlib.sha256(f"{secret}|web|{ip}".encode("utf-8")).hexdigest()
    return digest[:32]


def _resolve_site_by_slug(db: Session, site_slug: str) -> WebSite:
    slug = normalize_slug(site_slug)
    site = (
        db.query(WebSite)
        .filter(WebSite.site_slug == slug, WebSite.status != WebSiteStatus.DELETED)
        .first()
    )
    if not site:
        raise HTTPException(status_code=404, detail="Site não encontrado")
    return site


def _throttle(request: Request, db: Session) -> None:
    ip = auth_throttle.client_ip(request)
    auth_throttle.raise_if_limited(
        auth_throttle.check_lock(db, WEB_ANALYTICS_SCOPE, ip)
    )
    retry = auth_throttle.add_hit(db, WEB_ANALYTICS_SCOPE, ip, ip=ip, failed=False)
    auth_throttle.raise_if_limited(retry)


def _is_bot(request: Request) -> bool:
    ua = request.headers.get("user-agent") or ""
    return bool(_BOT_UA.search(ua))


def record_page_view(
    db: Session,
    request: Request,
    *,
    site_slug: str,
    visitor_id: str = "",
) -> bool:
    if _is_bot(request):
        return False
    _throttle(request, db)
    site = _resolve_site_by_slug(db, site_slug)
    if not load_config(site):
        return False
    ip = auth_throttle.client_ip(request)
    event = WebSiteAnalyticsEvent(
        site_id=site.id,
        event_type="page_view",
        link_id=None,
        link_label="",
        visitor_key=_visitor_key(visitor_id, ip),
    )
    db.add(event)
    db.flush()
    return True


def record_link_click(
    db: Session,
    request: Request,
    *,
    site: WebSite,
    link: WebPageLink,
    visitor_id: str = "",
) -> None:
    if _is_bot(request):
        return
    _throttle(request, db)
    ip = auth_throttle.client_ip(request)
    db.add(
        WebSiteAnalyticsEvent(
            site_id=site.id,
            event_type="link_click",
            link_id=link.id,
            link_label=_clip(link.label, 80),
            visitor_key=_visitor_key(visitor_id, ip),
        )
    )
    db.flush()


def resolve_click_redirect(
    db: Session,
    request: Request,
    *,
    site_slug: str,
    link_id: str,
) -> str:
    site = _resolve_site_by_slug(db, site_slug)
    config = load_config(site)
    if not config:
        raise HTTPException(status_code=404, detail="Página não encontrada")
    link = next((item for item in config.links if item.id == link_id), None)
    if not link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    record_link_click(db, request, site=site, link=link)
    db.commit()
    return link.url


def collect_stats(db: Session, site: WebSite, days: int = 30) -> dict[str, Any]:
    window = days if days in ALLOWED_DAYS else 30
    since = datetime.utcnow() - timedelta(days=window)
    rows = (
        db.query(WebSiteAnalyticsEvent)
        .filter(
            WebSiteAnalyticsEvent.site_id == site.id,
            WebSiteAnalyticsEvent.created_at >= since,
        )
        .all()
    )
    page_views = 0
    link_clicks = 0
    visitors: set[str] = set()
    daily_views: dict[str, int] = defaultdict(int)
    daily_clicks: dict[str, int] = defaultdict(int)
    daily_visitors: dict[str, set[str]] = defaultdict(set)
    link_counts: dict[str, dict[str, Any]] = {}

    for row in rows:
        day = row.created_at.strftime("%Y-%m-%d")
        if row.visitor_key:
            visitors.add(row.visitor_key)
            daily_visitors[day].add(row.visitor_key)
        if row.event_type == "page_view":
            page_views += 1
            daily_views[day] += 1
        elif row.event_type == "link_click":
            link_clicks += 1
            daily_clicks[day] += 1
            key = row.link_id or ""
            bucket = link_counts.setdefault(
                key,
                {"link_id": key, "label": row.link_label or key or "Link", "clicks": 0},
            )
            if row.link_label:
                bucket["label"] = row.link_label
            bucket["clicks"] += 1

    config = load_config(site)
    if config:
        for link in config.links:
            bucket = link_counts.setdefault(
                link.id,
                {"link_id": link.id, "label": link.label, "clicks": 0},
            )
            bucket["label"] = link.label

    all_days = sorted(set(daily_views) | set(daily_clicks) | set(daily_visitors))
    if not all_days:
        for offset in range(window):
            day = (datetime.utcnow() - timedelta(days=window - 1 - offset)).strftime("%Y-%m-%d")
            all_days.append(day)
    else:
        start = datetime.utcnow() - timedelta(days=window - 1)
        all_days = []
        for offset in range(window):
            all_days.append((start + timedelta(days=offset)).strftime("%Y-%m-%d"))

    daily = [
        {
            "date": day,
            "page_views": daily_views.get(day, 0),
            "link_clicks": daily_clicks.get(day, 0),
            "unique_visitors": len(daily_visitors.get(day, set())),
        }
        for day in all_days
    ]
    links = sorted(
        link_counts.values(),
        key=lambda item: (-int(item["clicks"]), str(item["label"])),
    )
    ctr = round((link_clicks / page_views) * 100, 1) if page_views else 0.0
    return {
        "days": window,
        "generated_at": datetime.utcnow(),
        "page_views": page_views,
        "link_clicks": link_clicks,
        "unique_visitors": len(visitors),
        "click_rate_pct": ctr,
        "daily": daily,
        "links": links,
    }


def delete_for_site(db: Session, site_id: int) -> None:
    db.query(WebSiteAnalyticsEvent).filter(WebSiteAnalyticsEvent.site_id == site_id).delete(
        synchronize_session=False
    )
