"""Slug e URL pública para sites sem domínio próprio (/s/nome ou slug.ruts.dev)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi import HTTPException

from app.config import Settings, get_settings

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_RESERVED = frozenset(
    {
        "api",
        "admin",
        "cyberhost",
        "dashboard",
        "financeiro",
        "login",
        "order",
        "register",
        "pixdev",
        "account",
        "sw",
        "s",
        "www",
    }
)


def normalize_slug(raw: str) -> str:
    slug = (raw or "").strip().lower()
    slug = slug.replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if len(slug) < 2 or len(slug) > 63 or not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Nome do site inválido. Use letras minúsculas, números e hífen (ex.: minha-loja)",
        )
    if slug in _RESERVED:
        raise HTTPException(status_code=400, detail="Este nome de site não está disponível")
    return slug


def path_prefix(slug: str) -> str:
    return f"/s/{normalize_slug(slug)}"


def resolved_public_base(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    raw = (settings.web_public_base_url or "").strip().rstrip("/")
    if raw:
        return raw
    frontend = settings.resolved_frontend_url.rstrip("/")
    if frontend.endswith("/cyberhost"):
        frontend = frontend[: -len("/cyberhost")]
    if frontend:
        return frontend
    ip = (settings.vps_public_ip or "").strip()
    if ip:
        return f"http://{ip}"
    return frontend


def platform_base_domain(settings: Settings | None = None) -> str:
    """Domínio raiz da plataforma (ex.: ruts.dev) para subdomínios automáticos."""
    settings = settings or get_settings()
    explicit = (getattr(settings, "web_platform_base_domain", None) or "").strip().lower().lstrip(".")
    if explicit:
        return explicit
    base = resolved_public_base(settings)
    if "://" not in base:
        base = f"https://{base}"
    host = (urlparse(base).hostname or "").lower()
    if not host or _IPV4_RE.match(host):
        return ""
    return host


def platform_subdomains_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not bool(getattr(settings, "web_platform_subdomains_enabled", True)):
        return False
    return bool(platform_base_domain(settings))


def platform_subdomain_for_site(site, settings: Settings | None = None) -> str | None:
    """Host automático slug.plataforma (ex.: minha-loja.ruts.dev) quando sem domínio próprio."""
    if (getattr(site, "domain", None) or "").strip():
        return None
    if not platform_subdomains_enabled(settings):
        return None
    base = platform_base_domain(settings)
    slug = (getattr(site, "site_slug", None) or "").strip().lower()
    if not base or not slug:
        return None
    return f"{slug}.{base}"


def platform_slug_from_host(host: str, settings: Settings | None = None) -> str | None:
    """Extrai slug de um host slug.plataforma (ex.: loja.ruts.dev → loja)."""
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    base = platform_base_domain(settings)
    if not base or not normalized.endswith(f".{base}"):
        return None
    slug = normalized[: -(len(base) + 1)]
    if not slug or "." in slug:
        return None
    try:
        normalize_slug(slug)
    except HTTPException:
        return None
    return slug


def dns_target_host(settings: Settings | None = None) -> str:
    """Host (IP ou domínio) para o cliente apontar o DNS do domínio próprio."""
    base = resolved_public_base(settings)
    if "://" not in base:
        base = f"http://{base}"
    host = urlparse(base).hostname
    return host or ""


def site_public_url(site, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    domain = (getattr(site, "domain", None) or "").strip()
    if domain:
        scheme = "http"
        if settings.web_ssl_enabled:
            from app.services.web_ssl import ssl_active_for_site

            if ssl_active_for_site(site, settings):
                scheme = "https"
        return f"{scheme}://{domain}"
    platform = platform_subdomain_for_site(site, settings)
    if platform:
        scheme = "https" if settings.web_ssl_enabled else "http"
        if settings.web_ssl_enabled:
            from app.services.web_ssl import ssl_active_for_site

            if not ssl_active_for_site(site, settings):
                scheme = "http"
        return f"{scheme}://{platform}/"
    slug = (getattr(site, "site_slug", None) or "").strip()
    if not slug:
        return resolved_public_base(settings)
    return f"{resolved_public_base(settings)}{path_prefix(slug)}/"
