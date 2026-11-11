"""Snippets nginx por site (HTTP 80 / HTTPS 443 → 127.0.0.1:porta)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import Settings, get_settings
from app.models.web_site import WebSite
from app.services.web_domain import normalize_domain
from app.services.web_slug import (
    normalize_slug,
    path_prefix,
    platform_subdomain_for_site,
)

logger = logging.getLogger(__name__)


def _snippet_dir(settings: Settings) -> Path:
    root = Path(settings.web_nginx_snippet_dir)
    if not root.is_absolute():
        root = Path(settings.web_sites_data_path) / "nginx"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _paths_dir(settings: Settings) -> Path:
    root = _snippet_dir(settings) / "paths"
    root.mkdir(parents=True, exist_ok=True)
    return root


def snippet_path(site: WebSite, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return _snippet_dir(settings) / f"site-{int(site.id)}.conf"


def path_snippet_path(site: WebSite, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return _paths_dir(settings) / f"site-{int(site.id)}.conf"


def _validate_port(site: WebSite, settings: Settings) -> int:
    port = int(site.port)
    start = int(settings.web_port_range_start)
    end = int(settings.web_port_range_end)
    if port < start or port > end:
        raise ValueError("porta fora do pool interno")
    return port


def _proxy_block(port: int, *, indent: str = "        ") -> str:
    return (
        f"{indent}proxy_pass http://127.0.0.1:{port}/;\n"
        f"{indent}proxy_http_version 1.1;\n"
        f"{indent}proxy_set_header Host $host;\n"
        f"{indent}proxy_set_header X-Real-IP $remote_addr;\n"
        f"{indent}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"{indent}proxy_set_header X-Forwarded-Proto $scheme;\n"
    )


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


def _resolve_vhost_domain(site: WebSite, settings: Settings) -> tuple[str, bool] | None:
    domain_raw = (site.domain or "").strip()
    if domain_raw:
        return normalize_domain(domain_raw), True
    platform = platform_subdomain_for_site(site, settings)
    if platform:
        return platform, False
    return None


def write_path_snippet(site: WebSite, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    slug = normalize_slug(site.site_slug)
    prefix = path_prefix(slug)
    port = _validate_port(site, settings)
    platform = platform_subdomain_for_site(site, settings)
    if platform:
        body = (
            "# gerado pelo painel CyberHost — não edite\n"
            f"location = {prefix} {{\n"
            f"    return 301 https://{platform}/;\n"
            "}\n"
            f"location {prefix}/ {{\n"
            f"    return 301 https://{platform}/;\n"
            "}\n"
        )
    else:
        body = (
            "# gerado pelo painel CyberHost — não edite\n"
            f"location = {prefix} {{\n"
            f"    return 301 {prefix}/;\n"
            "}\n"
            f"location {prefix}/ {{\n"
            f"{_proxy_block(port)}"
            "    }\n"
        )
    path = path_snippet_path(site, settings)
    path.write_text(body, encoding="utf-8")
    return path


def write_vhost_snippet(site: WebSite, settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    resolved = _resolve_vhost_domain(site, settings)
    if not resolved:
        remove_vhost_snippet(site, settings)
        return None
    domain, include_www = resolved
    port = _validate_port(site, settings)
    names = f"{domain} www.{domain}" if include_www else domain
    acme = _acme_location(settings)
    cert = None
    if settings.web_ssl_enabled:
        from app.services.web_ssl import cert_paths

        cert = cert_paths(site.id)
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
            "    client_max_body_size 32m;\n"
            "    location / {\n"
            f"{_proxy_block(port)}"
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
            "    client_max_body_size 32m;\n"
            f"{acme}"
            "    location / {\n"
            f"{_proxy_block(port)}"
            "    }\n"
            "}\n"
        )
    path = snippet_path(site, settings)
    path.write_text(body, encoding="utf-8")
    return path


def write_domain_snippet(site: WebSite, settings: Settings | None = None) -> Path | None:
    return write_vhost_snippet(site, settings)


def write_snippet(site: WebSite, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    write_path_snippet(site, settings)
    write_vhost_snippet(site, settings)


def remove_vhost_snippet(site: WebSite, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = snippet_path(site, settings)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("não removeu snippet de vhost site=%s", site.id)


def remove_domain_snippet(site: WebSite, settings: Settings | None = None) -> None:
    remove_vhost_snippet(site, settings)


def remove_path_snippet(site: WebSite, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = path_snippet_path(site, settings)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("não removeu snippet de path site=%s", site.id)


def remove_snippet(site: WebSite, settings: Settings | None = None) -> None:
    remove_vhost_snippet(site, settings)
    remove_path_snippet(site, settings)


def reload_nginx(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.web_nginx_reload:
        return
    test = subprocess.run(
        ["sudo", "-n", "nginx", "-t"],
        check=False,
        capture_output=True,
        text=True,
    )
    if test.returncode != 0:
        err = (test.stderr or test.stdout or "nginx -t falhou").strip()
        raise RuntimeError(err[:400])
    reload = subprocess.run(
        ["sudo", "-n", "systemctl", "reload", "nginx"],
        check=False,
        capture_output=True,
        text=True,
    )
    if reload.returncode != 0:
        err = (reload.stderr or reload.stdout or "reload nginx falhou").strip()
        raise RuntimeError(err[:400])
