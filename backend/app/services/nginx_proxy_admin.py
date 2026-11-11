"""Proxy nginx: listagem agregada e rotas manuais do administrador."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.nginx_proxy import NginxProxyRoute
from app.models.vps import VpsInstance, VpsStatus
from app.models.vps_connection import VpsConnectionDomain
from app.models.web_site import WebSite, WebSiteStatus
from app.services.port_proxy import resolved_vps_public_ip
from app.services.vps_connection_domains import remove_connection_domain
from app.services.web_domain import domain_in_use, normalize_domain
from app.services.web_nginx import reload_nginx
from app.services.web_slug import platform_subdomain_for_site
from app.services.web_ssl import configure_domain as configure_site_domain

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _snippet_dir(settings: Settings) -> Path:
    root = Path(settings.web_nginx_snippet_dir)
    if not root.is_absolute():
        root = Path(settings.web_sites_data_path) / "nginx"
    root.mkdir(parents=True, exist_ok=True)
    return root


def manual_snippet_path(route_id: int, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return _snippet_dir(settings) / f"manual-{int(route_id)}.conf"


def manual_cert_name(route_id: int) -> str:
    return f"cyberhost-proxy-{int(route_id)}"


def manual_cert_paths(route_id: int) -> tuple[Path, Path] | None:
    name = manual_cert_name(route_id)
    proc = subprocess.run(
        ["sudo", "-n", "certbot", "certificates", "--cert-name", name],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout or ""
    if f"Certificate Name: {name}" not in out:
        return None
    return (
        Path(f"/etc/letsencrypt/live/{name}/fullchain.pem"),
        Path(f"/etc/letsencrypt/live/{name}/privkey.pem"),
    )


def _ssl_email(settings: Settings) -> str:
    for raw in (settings.web_ssl_email, settings.smtp_from):
        match = _EMAIL_RE.search((raw or "").strip())
        if match:
            return match.group(1)
    return ""


def _acme_location(settings: Settings) -> str:
    webroot = (settings.web_acme_webroot or "/var/www/acme").strip() or "/var/www/acme"
    return (
        "    location ^~ /.well-known/acme-challenge/ {\n"
        f"        root {webroot};\n"
        "        try_files $uri =404;\n"
        "    }\n"
    )


def _ssl_directives(cert_full: Path, cert_key: Path) -> str:
    lines = [
        f"    ssl_certificate {cert_full};",
        f"    ssl_certificate_key {cert_key};",
    ]
    opts = Path("/etc/letsencrypt/options-ssl-nginx.conf")
    dh = Path("/etc/letsencrypt/ssl-dhparams.pem")
    if opts.is_file():
        lines.append("    include /etc/letsencrypt/options-ssl-nginx.conf;")
    if dh.is_file():
        lines.append("    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;")
    return "\n".join(lines) + "\n"


def _normalize_upstream(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="URL de destino inválida")
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL de destino inválida")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _normalize_redirect(url: str) -> str:
    raw = (url or "").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL de redirecionamento deve começar com http:// ou https://")
    return raw


def _location_block(route: NginxProxyRoute) -> str:
    if route.mode == "redirect":
        target = _normalize_redirect(route.redirect_url or "")
        return f"        return 301 {target};\n"
    upstream = _normalize_upstream(route.upstream_url or "")
    return (
        f"        proxy_pass {upstream};\n"
        "        proxy_http_version 1.1;\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Real-IP $remote_addr;\n"
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        "        proxy_set_header X-Forwarded-Proto $scheme;\n"
    )


def write_manual_snippet(route: NginxProxyRoute, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    domain = normalize_domain(route.domain)
    names = f"{domain} www.{domain}" if route.include_www else domain
    acme = _acme_location(settings)
    location = _location_block(route)
    cert = manual_cert_paths(route.id) if settings.web_ssl_enabled else None
    if cert:
        cert_full, cert_key = cert
        body = (
            "# gerado pelo painel CyberHost — não edite\n"
            "server {\n"
            "    listen 80;\n"
            "    listen [::]:80;\n"
            f"    server_name {names};\n"
            f"{acme}"
            "    location / {\n"
            "        return 301 https://$host$request_uri;\n"
            "    }\n"
            "}\n"
            "server {\n"
            "    listen 443 ssl http2;\n"
            "    listen [::]:443 ssl http2;\n"
            f"    server_name {names};\n"
            f"{_ssl_directives(cert_full, cert_key)}"
            "    client_max_body_size 64m;\n"
            "    location / {\n"
            f"{location}"
            "    }\n"
            "}\n"
        )
    else:
        body = (
            "# gerado pelo painel CyberHost — não edite\n"
            "server {\n"
            "    listen 80;\n"
            "    listen [::]:80;\n"
            f"    server_name {names};\n"
            "    client_max_body_size 64m;\n"
            f"{acme}"
            "    location / {\n"
            f"{location}"
            "    }\n"
            "}\n"
        )
    path = manual_snippet_path(route.id, settings)
    path.write_text(body, encoding="utf-8")
    return path


def remove_manual_snippet(route_id: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    try:
        manual_snippet_path(route_id, settings).unlink(missing_ok=True)
    except OSError:
        logger.warning("não removeu snippet manual-%s", route_id)


def ensure_manual_certificate(route: NginxProxyRoute, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.web_ssl_enabled:
        return False
    if manual_cert_paths(route.id):
        return True
    email = _ssl_email(settings)
    if not email:
        return False
    domain = normalize_domain(route.domain)
    webroot = Path(settings.web_acme_webroot)
    webroot.mkdir(parents=True, exist_ok=True)
    certbot = (settings.web_certbot_binary or "/usr/bin/certbot").strip() or "/usr/bin/certbot"
    cmd = [
        "sudo",
        "-n",
        certbot,
        "certonly",
        "--webroot",
        "-w",
        str(webroot),
        "-d",
        domain,
    ]
    if route.include_www:
        cmd.extend(["-d", f"www.{domain}"])
    cmd.extend(
        [
            "--email",
            email,
            "--agree-tos",
            "--non-interactive",
            "--cert-name",
            manual_cert_name(route.id),
            "--keep-until-expiring",
        ]
    )
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "certbot falhou").strip()
        logger.warning("proxy SSL id=%s domínio=%s: %s", route.id, domain, err[:500])
        return False
    return manual_cert_paths(route.id) is not None


def apply_manual_route(route: NginxProxyRoute, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    write_manual_snippet(route, settings)
    reload_nginx(settings)
    if not settings.web_ssl_enabled:
        return False
    if not ensure_manual_certificate(route, settings):
        return bool(manual_cert_paths(route.id))
    write_manual_snippet(route, settings)
    reload_nginx(settings)
    return bool(manual_cert_paths(route.id))


def _site_target(site: WebSite, settings: Settings) -> str:
    return f"http://127.0.0.1:{int(site.port)}/"


def _vps_target(conn: VpsConnectionDomain, settings: Settings) -> str:
    host = resolved_vps_public_ip(settings)
    return f"http://{host}:{int(conn.public_port)}/"


def _site_hosts(site: WebSite, settings: Settings) -> list[tuple[str, str, str, bool, bool]]:
    entries: list[tuple[str, str, str, bool, bool]] = []
    platform = platform_subdomain_for_site(site, settings)
    if platform:
        from app.services.web_ssl import ssl_active_for_site

        entries.append(
            (
                platform,
                "reverse_proxy",
                _site_target(site, settings),
                ssl_active_for_site(site, settings),
                False,
            )
        )
    if (site.domain or "").strip():
        from app.services.web_ssl import ssl_active_for_site

        entries.append(
            (
                normalize_domain(site.domain),
                "reverse_proxy",
                _site_target(site, settings),
                ssl_active_for_site(site, settings),
                True,
            )
        )
    return entries


def list_proxy_entries(db: Session, settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    items: list[dict] = []

    for route in db.query(NginxProxyRoute).order_by(NginxProxyRoute.domain.asc()).all():
        target = (
            _normalize_redirect(route.redirect_url or "")
            if route.mode == "redirect"
            else _normalize_upstream(route.upstream_url or "")
        )
        items.append(
            {
                "key": f"manual-{route.id}",
                "kind": "manual",
                "reference_id": route.id,
                "domain": route.domain,
                "mode": route.mode,
                "target": target,
                "include_www": route.include_www,
                "ssl_active": bool(manual_cert_paths(route.id)),
                "editable": True,
                "deletable": True,
                "label": "Proxy manual",
                "notes": route.notes,
                "created_at": route.created_at,
            }
        )

    sites = (
        db.query(WebSite)
        .filter(WebSite.status != WebSiteStatus.DELETED)
        .order_by(WebSite.id.asc())
        .all()
    )
    for site in sites:
        slug = site.site_slug or f"site-{site.id}"
        for domain, mode, target, ssl_active, is_custom in _site_hosts(site, settings):
            items.append(
                {
                    "key": f"site-{site.id}-{'custom' if is_custom else 'platform'}",
                    "kind": "web_site",
                    "reference_id": site.id,
                    "domain": domain,
                    "mode": mode,
                    "target": target,
                    "include_www": is_custom,
                    "ssl_active": ssl_active,
                    "editable": is_custom,
                    "deletable": is_custom,
                    "label": f"Site {slug}" + (" (domínio próprio)" if is_custom else " (subdomínio)"),
                    "notes": None,
                    "created_at": site.created_at,
                }
            )

    conns = (
        db.query(VpsConnectionDomain, VpsInstance)
        .join(VpsInstance, VpsInstance.id == VpsConnectionDomain.vps_instance_id)
        .filter(VpsInstance.status != VpsStatus.DELETED)
        .order_by(VpsConnectionDomain.domain.asc())
        .all()
    )
    for conn, instance in conns:
        from app.services.vps_connection_ssl import has_certificate as vps_ssl

        items.append(
            {
                "key": f"vps-{conn.id}",
                "kind": "vps_connection",
                "reference_id": conn.id,
                "domain": conn.domain,
                "mode": "reverse_proxy",
                "target": _vps_target(conn, settings),
                "include_www": False,
                "ssl_active": vps_ssl(conn),
                "editable": True,
                "deletable": True,
                "label": f"VPS {instance.vm_name} :{conn.public_port}",
                "notes": None,
                "created_at": conn.created_at,
            }
        )

    items.sort(key=lambda row: row["domain"])
    return items


def create_manual_route(db: Session, payload) -> NginxProxyRoute:
    domain = normalize_domain(payload.domain)
    if domain_in_use(db, domain):
        raise HTTPException(status_code=400, detail="Este domínio já está em uso")
    upstream = None
    redirect = None
    if payload.mode == "reverse_proxy":
        upstream = _normalize_upstream(payload.upstream_url or "")
    else:
        redirect = _normalize_redirect(payload.redirect_url or "")
    route = NginxProxyRoute(
        domain=domain,
        mode=payload.mode,
        upstream_url=upstream,
        redirect_url=redirect,
        include_www=bool(payload.include_www),
        notes=(payload.notes or "").strip() or None,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    try:
        apply_manual_route(route)
    except Exception as exc:
        db.delete(route)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
    return route


def update_manual_route(db: Session, route_id: int, payload) -> NginxProxyRoute:
    route = db.get(NginxProxyRoute, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Proxy não encontrado")
    if payload.domain is not None:
        domain = normalize_domain(payload.domain)
        if domain != route.domain and domain_in_use(db, domain, ignore_manual_proxy_id=route_id):
            raise HTTPException(status_code=400, detail="Este domínio já está em uso")
        route.domain = domain
    if payload.mode is not None:
        route.mode = payload.mode
    if payload.include_www is not None:
        route.include_www = payload.include_www
    if payload.notes is not None:
        route.notes = payload.notes.strip() or None
    mode = route.mode
    if payload.mode is not None:
        mode = payload.mode
    if mode == "reverse_proxy":
        if payload.upstream_url is not None:
            route.upstream_url = _normalize_upstream(payload.upstream_url)
        route.redirect_url = None
    elif mode == "redirect":
        if payload.redirect_url is not None:
            route.redirect_url = _normalize_redirect(payload.redirect_url)
        route.upstream_url = None
    db.commit()
    db.refresh(route)
    try:
        apply_manual_route(route)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
    return route


def delete_manual_route(db: Session, route_id: int) -> None:
    route = db.get(NginxProxyRoute, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Proxy não encontrado")
    remove_manual_snippet(route.id)
    db.delete(route)
    db.commit()
    try:
        reload_nginx()
    except Exception:
        pass


def update_system_proxy(db: Session, kind: str, reference_id: int, domain: str) -> None:
    normalized = normalize_domain(domain)
    if kind == "web_site":
        site = db.get(WebSite, reference_id)
        if not site or site.status == WebSiteStatus.DELETED:
            raise HTTPException(status_code=404, detail="Site não encontrado")
        if domain_in_use(db, normalized, ignore_site_id=site.id):
            raise HTTPException(status_code=400, detail="Este domínio já está em uso")
        site.domain = normalized
        db.commit()
        try:
            configure_site_domain(site)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
        return
    if kind == "vps_connection":
        from app.services.vps_connection_domains import upsert_connection_domain
        from app.models.user import User

        conn = db.get(VpsConnectionDomain, reference_id)
        if not conn:
            raise HTTPException(status_code=404, detail="Conexão não encontrada")
        instance = db.get(VpsInstance, conn.vps_instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="VPS não encontrada")
        user = db.get(User, conn.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        upsert_connection_domain(
            db,
            instance,
            user,
            domain_raw=normalized,
            public_port=conn.public_port,
        )
        return
    raise HTTPException(status_code=400, detail="Tipo de proxy inválido")


def delete_system_proxy(db: Session, kind: str, reference_id: int) -> None:
    if kind == "web_site":
        site = db.get(WebSite, reference_id)
        if not site or site.status == WebSiteStatus.DELETED:
            raise HTTPException(status_code=404, detail="Site não encontrado")
        if not (site.domain or "").strip():
            raise HTTPException(status_code=400, detail="Site não possui domínio próprio para remover")
        site.domain = None
        db.commit()
        configure_site_domain(site)
        return
    if kind == "vps_connection":
        conn = db.get(VpsConnectionDomain, reference_id)
        if not conn:
            raise HTTPException(status_code=404, detail="Conexão não encontrada")
        instance = db.get(VpsInstance, conn.vps_instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="VPS não encontrada")
        remove_connection_domain(db, instance, conn.id)
        return
    raise HTTPException(status_code=400, detail="Tipo de proxy inválido")
