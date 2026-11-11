"""Certificados Let's Encrypt para domínios de conexão VPS."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import Settings, get_settings
from app.models.vps_connection import VpsConnectionDomain
from app.services.vps_nginx import apply_snippet, supports_http_proxy, write_snippet
from app.services.web_domain import normalize_domain
from app.services.web_nginx import reload_nginx
from app.services.web_ssl import ssl_contact_email

logger = logging.getLogger(__name__)


def cert_name(connection_id: int) -> str:
    return f"cyberhost-vps-conn-{int(connection_id)}"


def cert_paths(connection_id: int) -> tuple[Path, Path] | None:
    name = cert_name(connection_id)
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
    full = Path(f"/etc/letsencrypt/live/{name}/fullchain.pem")
    key = Path(f"/etc/letsencrypt/live/{name}/privkey.pem")
    return full, key


def has_certificate(conn: VpsConnectionDomain) -> bool:
    return cert_paths(int(conn.id)) is not None


def ensure_certificate(conn: VpsConnectionDomain, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.web_ssl_enabled or not supports_http_proxy(conn.internal_port):
        return False
    domain = normalize_domain(conn.domain)
    if not domain:
        return False
    if cert_paths(conn.id):
        return True
    email = ssl_contact_email(settings)
    if not email:
        logger.warning("vps conn SSL: defina WEB_SSL_EMAIL ou SMTP_FROM")
        return False
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
        "-d",
        f"www.{domain}",
        "--email",
        email,
        "--agree-tos",
        "--non-interactive",
        "--cert-name",
        cert_name(conn.id),
        "--keep-until-expiring",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "certbot falhou").strip()
        logger.warning("vps conn SSL id=%s domínio=%s: %s", conn.id, domain, err[:500])
        return False
    return cert_paths(conn.id) is not None


def configure_domain(conn: VpsConnectionDomain, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    write_snippet(conn, settings)
    reload_nginx(settings)
    if not supports_http_proxy(conn.internal_port):
        return False
    if not ensure_certificate(conn, settings):
        return has_certificate(conn)
    write_snippet(conn, settings)
    try:
        reload_nginx(settings)
    except Exception as exc:
        logger.warning("nginx reload após SSL vps-conn=%s: %s", conn.id, exc)
    return has_certificate(conn)
