"""Certificados Let's Encrypt (webroot) para domínios de sites."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from app.config import Settings, get_settings
from app.models.web_site import WebSite
from app.services import web_nginx
from app.services.web_domain import normalize_domain
from app.services.web_slug import platform_subdomain_for_site

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def cert_name(site_id: int) -> str:
    return f"cyberhost-site-{int(site_id)}"


def _certbot_certificates_output(site_id: int) -> str | None:
    name = cert_name(site_id)
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
    return out


def cert_paths(site_id: int) -> tuple[Path, Path] | None:
    out = _certbot_certificates_output(site_id)
    if not out:
        return None
    name = cert_name(site_id)
    # Caminhos usados pelo nginx (root); não usar .is_file() — processo rts não lê live/.
    return (
        Path(f"/etc/letsencrypt/live/{name}/fullchain.pem"),
        Path(f"/etc/letsencrypt/live/{name}/privkey.pem"),
    )


def cert_domains(site_id: int) -> set[str]:
    out = _certbot_certificates_output(site_id)
    if not out:
        return set()
    domains: set[str] = set()
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Domains:"):
            rest = stripped.split(":", 1)[1].strip()
            domains.update(part.lower() for part in rest.split() if part)
    return domains


def public_site_host(site: WebSite, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    domain_raw = (site.domain or "").strip()
    if domain_raw:
        return normalize_domain(domain_raw)
    return platform_subdomain_for_site(site, settings)


def required_cert_domains(site: WebSite, settings: Settings | None = None) -> set[str]:
    host = public_site_host(site, settings)
    if not host:
        return set()
    host = host.lower()
    required = {host}
    if (site.domain or "").strip():
        required.add(f"www.{host}")
    return required


def certificate_covers_site(site: WebSite, settings: Settings | None = None) -> bool:
    if not cert_paths(int(site.id)):
        return False
    issued = cert_domains(int(site.id))
    if not issued:
        return False
    required = required_cert_domains(site, settings)
    return required.issubset(issued)


def has_certificate(site: WebSite) -> bool:
    """Arquivo de certificado existe (pode não cobrir o domínio atual)."""
    return cert_paths(int(site.id)) is not None


def ssl_active_for_site(site: WebSite, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not public_site_host(site, settings):
        return False
    return certificate_covers_site(site, settings)


def ssl_contact_email(settings: Settings) -> str:
    for raw in (settings.web_ssl_email, settings.smtp_from):
        match = _EMAIL_RE.search((raw or "").strip())
        if match:
            return match.group(1)
    return ""


def _delete_certificate(site_id: int) -> None:
    if not cert_paths(site_id):
        return
    subprocess.run(
        [
            "sudo",
            "-n",
            "certbot",
            "delete",
            "--cert-name",
            cert_name(site_id),
            "--non-interactive",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _site_id_from_cert_name(name: str) -> int | None:
    prefix = "cyberhost-site-"
    if not name.startswith(prefix):
        return None
    suffix = name[len(prefix) :].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def list_cyberhost_certificates() -> list[tuple[int, set[str]]]:
    """Todos os certificados cyberhost-site-* registrados no certbot."""
    proc = subprocess.run(
        ["sudo", "-n", "certbot", "certificates"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    entries: list[tuple[int, set[str]]] = []
    current_id: int | None = None
    current_domains: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Certificate Name:"):
            if current_id is not None:
                entries.append((current_id, current_domains))
            name = stripped.split(":", 1)[1].strip()
            current_id = _site_id_from_cert_name(name)
            current_domains = set()
        elif stripped.startswith("Domains:") and current_id is not None:
            rest = stripped.split(":", 1)[1].strip()
            current_domains.update(part.lower() for part in rest.split() if part)
    if current_id is not None:
        entries.append((current_id, current_domains))
    return entries


def release_certificate_for_site(site_id: int) -> None:
    """Remove certificado Let's Encrypt amarrado ao id do site."""
    _delete_certificate(int(site_id))


def _release_conflicting_certificates(site: WebSite, db) -> None:
    """
    Domínio reutilizado ou site apagado: cert antigo (outro cyberhost-site-N)
    não pode continuar reservando o nome no certbot.
    """
    from app.models.web_site import WebSiteStatus

    settings = get_settings()
    required = required_cert_domains(site, settings)
    if not required:
        return
    for cert_site_id, domains in list_cyberhost_certificates():
        if cert_site_id == int(site.id):
            continue
        if not domains.intersection(required):
            continue
        other = db.get(WebSite, cert_site_id) if db is not None else None
        if other is None or other.status == WebSiteStatus.DELETED:
            logger.info(
                "Removendo certificado órfão cyberhost-site-%s (domínio reutilizado no site %s)",
                cert_site_id,
                site.id,
            )
            _delete_certificate(cert_site_id)
            continue
        other_required = required_cert_domains(other, settings)
        if other_required.intersection(required):
            # Outro site ativo ainda usa o mesmo domínio — domain_in_use deveria impedir.
            continue
        logger.info(
            "Removendo certificado desatualizado cyberhost-site-%s (site %s agora usa %s)",
            cert_site_id,
            site.id,
            ", ".join(sorted(required)),
        )
        _delete_certificate(cert_site_id)


def ensure_certificate(
    site: WebSite,
    settings: Settings | None = None,
    *,
    db=None,
) -> tuple[bool, str | None]:
    settings = settings or get_settings()
    if not settings.web_ssl_enabled:
        return False, "SSL desabilitado no servidor (WEB_SSL_ENABLED=false)"
    domain = public_site_host(site, settings)
    if not domain:
        return False, "Site sem domínio ou subdomínio da plataforma"
    if db is None:
        from sqlalchemy.orm import object_session

        db = object_session(site)
    if db is not None:
        _release_conflicting_certificates(site, db)
    if cert_paths(site.id) and certificate_covers_site(site, settings):
        return True, None
    if cert_paths(site.id):
        _delete_certificate(site.id)
    email = ssl_contact_email(settings)
    if not email:
        return False, "Defina WEB_SSL_EMAIL ou SMTP_FROM no servidor para emitir certificado"
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
    if (site.domain or "").strip():
        cmd.extend(["-d", f"www.{domain}"])
    cmd.extend(
        [
            "--email",
            email,
            "--agree-tos",
            "--non-interactive",
            "--cert-name",
            cert_name(site.id),
            "--keep-until-expiring",
        ]
    )
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "certbot falhou").strip()
        logger.warning("web SSL site=%s domínio=%s: %s", site.id, domain, err[:500])
        hint = (
            "Verifique se o DNS aponta para este servidor. "
            "Com Cloudflare, use 'Somente DNS' (nuvem cinza) até o certificado ser emitido."
        )
        short = err.splitlines()[-1][:200] if err else "certbot falhou"
        return False, f"{short}. {hint}"
    if certificate_covers_site(site, settings):
        return True, None
    return False, "Certificado emitido, mas não cobre o domínio configurado"


def try_enable_https(
    site: WebSite,
    settings: Settings | None = None,
    *,
    db=None,
) -> tuple[bool, str | None]:
    settings = settings or get_settings()
    if not public_site_host(site, settings) or not settings.web_ssl_enabled:
        return False, None
    ok, err = ensure_certificate(site, settings, db=db)
    if not ok and not certificate_covers_site(site, settings):
        return False, err
    web_nginx.write_vhost_snippet(site, settings)
    try:
        web_nginx.reload_nginx(settings)
    except Exception as exc:
        logger.warning("nginx reload após SSL site=%s: %s", site.id, exc)
        return certificate_covers_site(site, settings), str(exc)[:400]
    return certificate_covers_site(site, settings), err if not ok else None


def configure_domain(site: WebSite, settings: Settings | None = None) -> bool:
    """Atualiza nginx do domínio/subdomínio e tenta emitir HTTPS."""
    ok, _ = configure_domain_with_status(site, settings)
    return ok


def configure_domain_with_status(
    site: WebSite,
    settings: Settings | None = None,
    *,
    db=None,
) -> tuple[bool, str | None]:
    settings = settings or get_settings()
    web_nginx.write_snippet(site, settings)
    web_nginx.reload_nginx(settings)
    return try_enable_https(site, settings, db=db)
