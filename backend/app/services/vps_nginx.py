"""Snippets nginx: domínio do cliente → porta pública da VPS (HTTP/HTTPS)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import Settings, get_settings
from app.models.vps_connection import VpsConnectionDomain
from app.services.port_proxy import resolved_vps_public_ip
from app.services.web_domain import normalize_domain
from app.services.web_nginx import reload_nginx

logger = logging.getLogger(__name__)

HTTP_PROXY_INTERNAL_PORTS = frozenset({80, 443, 8080, 8000, 3000, 3001, 8443, 8888, 5000, 9000})


def supports_http_proxy(internal_port: int) -> bool:
    return int(internal_port) in HTTP_PROXY_INTERNAL_PORTS


def _snippet_dir(settings: Settings) -> Path:
    root = Path(settings.web_nginx_snippet_dir)
    if not root.is_absolute():
        root = Path(settings.web_sites_data_path) / "nginx"
    root.mkdir(parents=True, exist_ok=True)
    return root


def snippet_path(conn: VpsConnectionDomain, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return _snippet_dir(settings) / f"vps-conn-{int(conn.id)}.conf"


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


def _upstream_base(conn: VpsConnectionDomain, settings: Settings) -> tuple[str, bool]:
    host = resolved_vps_public_ip(settings)
    port = int(conn.public_port)
    https = int(conn.internal_port) == 443
    scheme = "https" if https else "http"
    return f"{scheme}://{host}:{port}", https


def _proxy_block(upstream: str, *, https_upstream: bool) -> str:
    lines = [
        f"        proxy_pass {upstream}/;",
        "        proxy_http_version 1.1;",
        "        proxy_set_header Host $host;",
        "        proxy_set_header X-Real-IP $remote_addr;",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_set_header X-Forwarded-Proto $scheme;",
    ]
    if https_upstream:
        lines.extend(
            [
                "        proxy_ssl_server_name on;",
                "        proxy_ssl_verify off;",
            ]
        )
    return "\n".join(f"{line}\n" for line in lines)


def write_snippet(conn: VpsConnectionDomain, settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    if not supports_http_proxy(conn.internal_port):
        remove_snippet(conn, settings)
        return None
    domain = normalize_domain(conn.domain)
    names = f"{domain} www.{domain}"
    upstream, https_upstream = _upstream_base(conn, settings)
    acme = _acme_location(settings)
    cert = None
    if settings.web_ssl_enabled:
        from app.services.vps_connection_ssl import cert_paths

        cert = cert_paths(conn.id)
    proxy = _proxy_block(upstream, https_upstream=https_upstream)
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
            f"{proxy}"
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
            f"{proxy}"
            "    }\n"
            "}\n"
        )
    path = snippet_path(conn, settings)
    path.write_text(body, encoding="utf-8")
    return path


def remove_snippet(conn: VpsConnectionDomain, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = snippet_path(conn, settings)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("não removeu snippet vps-conn=%s", conn.id)


def apply_snippet(conn: VpsConnectionDomain, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    write_snippet(conn, settings)
    reload_nginx(settings)
