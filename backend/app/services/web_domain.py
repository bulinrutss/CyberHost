"""Validação de domínio para vhost nginx."""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_BLOCKED = frozenset({"localhost", "local", "invalid", "example", "test"})


def normalize_domain(raw: str) -> str:
    domain = (raw or "").strip().lower().rstrip(".")
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.split("://", 1)[1]
    domain = domain.split("/", 1)[0]
    domain = domain.split(":", 1)[0]
    if domain.startswith("www."):
        domain = domain[4:]
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(
            status_code=400,
            detail="Domínio inválido. Use algo como loja.seudominio.com.br",
        )
    tld = domain.rsplit(".", 1)[-1]
    if tld in _BLOCKED:
        raise HTTPException(status_code=400, detail="Domínio não permitido")
    labels = domain.split(".")
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        raise HTTPException(status_code=400, detail="Domínio inválido")
    return domain


def platform_subdomain_reserved(
    db: Session,
    domain: str,
    *,
    ignore_site_id: int | None = None,
) -> bool:
    """True se o domínio é slug.plataforma reservado por outro site."""
    from app.models.web_site import WebSite, WebSiteStatus
    from app.services.web_slug import platform_slug_from_host, platform_subdomains_enabled

    if not platform_subdomains_enabled():
        return False
    slug = platform_slug_from_host(domain)
    if not slug:
        return False
    query = db.query(WebSite).filter(
        WebSite.site_slug == slug,
        WebSite.status != WebSiteStatus.DELETED,
    )
    if ignore_site_id is not None:
        query = query.filter(WebSite.id != ignore_site_id)
    return query.first() is not None


def domain_in_use(
    db: Session,
    domain: str,
    *,
    ignore_site_id: int | None = None,
    ignore_order_id: int | None = None,
    ignore_vps_connection_id: int | None = None,
    ignore_manual_proxy_id: int | None = None,
) -> bool:
    from app.models.nginx_proxy import NginxProxyRoute
    from app.models.vps_connection import VpsConnectionDomain
    from app.models.web_site import WebOrder, WebOrderStatus, WebSite, WebSiteStatus

    site_q = db.query(WebSite).filter(
        WebSite.domain == domain,
        WebSite.status != WebSiteStatus.DELETED,
    )
    if ignore_site_id is not None:
        site_q = site_q.filter(WebSite.id != ignore_site_id)
    if site_q.first():
        return True
    conn_q = db.query(VpsConnectionDomain).filter(VpsConnectionDomain.domain == domain)
    if ignore_vps_connection_id is not None:
        conn_q = conn_q.filter(VpsConnectionDomain.id != ignore_vps_connection_id)
    if conn_q.first():
        return True
    manual_q = db.query(NginxProxyRoute).filter(NginxProxyRoute.domain == domain)
    if ignore_manual_proxy_id is not None:
        manual_q = manual_q.filter(NginxProxyRoute.id != ignore_manual_proxy_id)
    if manual_q.first():
        return True
    order_q = db.query(WebOrder).filter(
        WebOrder.domain == domain,
        WebOrder.status.in_(
            (
                WebOrderStatus.PENDING_PAYMENT,
                WebOrderStatus.PAID,
                WebOrderStatus.PROVISIONING,
                WebOrderStatus.ACTIVE,
            )
        ),
    )
    if ignore_order_id is not None:
        order_q = order_q.filter(WebOrder.id != ignore_order_id)
    for order in order_q.all():
        linked = db.query(WebSite).filter(WebSite.order_id == order.id).first()
        if linked and linked.status == WebSiteStatus.DELETED:
            continue
        return True
    return platform_subdomain_reserved(db, domain, ignore_site_id=ignore_site_id)
