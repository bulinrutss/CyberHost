"""Provisiona pasta, porta interna, nginx e processo do site."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.web_site import WebOrder, WebOrderStatus, WebSite, WebSiteStatus
from app.services.billing import initial_paid_until
from app.services import web_nginx
from app.services import web_process
from app.services.web_ssl import public_site_host, try_enable_https
from app.services.web_slug import path_prefix, site_public_url

logger = logging.getLogger(__name__)

INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Site no ar</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0b1220; color: #e2e8f0;
           min-height: 100vh; display: grid; place-items: center; margin: 0; }
    main { max-width: 32rem; padding: 2rem; }
    h1 { font-size: 1.6rem; }
    p { color: #94a3b8; line-height: 1.5; }
    code { color: #38bdf8; }
  </style>
</head>
<body>
  <main>
    <h1>Seu site está no ar</h1>
    <p>Envie os arquivos pelo painel CyberHost (pasta <code>public</code>).
       Seu site já está em <code>{{PUBLIC_URL}}</code>.
       Depois você pode apontar um domínio próprio (registro A) ou continuar só pelo link.</p>
  </main>
</body>
</html>
"""


def _update_progress(db: Session, order: WebOrder, *, progress: int, step: str) -> None:
    order.provision_progress = progress
    order.provision_step = step
    db.commit()


def allocate_port(db: Session) -> int:
    settings = get_settings()
    start = int(settings.web_port_range_start)
    end = int(settings.web_port_range_end)
    used = {
        row[0]
        for row in db.query(WebSite.port)
        .filter(WebSite.status != WebSiteStatus.DELETED)
        .all()
    }
    for port in range(start, end + 1):
        if port not in used:
            return port
    raise ValueError("Sem portas internas disponíveis para novos sites")


def _data_path(user_id: int, site_id: int) -> str:
    root = Path(get_settings().web_sites_data_path)
    return str(root / str(user_id) / str(site_id))


def provision_order(db: Session, order: WebOrder) -> WebSite:
    settings = get_settings()
    _update_progress(db, order, progress=20, step="allocating")
    port = allocate_port(db)
    paid_until, billing_day = initial_paid_until()
    site = WebSite(
        user_id=order.user_id,
        order_id=order.id,
        site_slug=order.site_slug,
        domain=order.domain,
        ram_mb=order.ram_mb,
        disk_mb=order.disk_mb,
        cpu_percent=order.cpu_percent,
        php_enabled=order.php_enabled,
        port=port,
        data_path="",
        status=WebSiteStatus.CREATING,
        paid_until=paid_until,
        billing_day=billing_day,
    )
    db.add(site)
    db.flush()
    site.data_path = _data_path(order.user_id, site.id)
    public = Path(site.data_path) / "public"
    public.mkdir(parents=True, exist_ok=True)
    index = public / "index.html"
    if not index.exists():
        index.write_text(
            INDEX_HTML.replace("{{PUBLIC_URL}}", site_public_url(site)),
            encoding="utf-8",
        )
    _update_progress(db, order, progress=55, step="writing_files")
    web_nginx.write_snippet(site)
    _update_progress(db, order, progress=70, step="starting")
    # Permissões do runtime (web_site_server.py) são ajustadas no spawn via sudo (root).
    try:
        web_process.start_site(site, settings)
    except Exception as exc:
        site.status = WebSiteStatus.ERROR
        site.error_message = str(exc)[:2000]
        db.commit()
        raise
    _update_progress(db, order, progress=90, step="nginx")
    try:
        web_nginx.reload_nginx(settings)
        if public_site_host(site, settings):
            try_enable_https(site, settings)
    except Exception as exc:
        logger.warning("nginx reload falhou site=%s: %s", site.id, exc)
        site.error_message = (
            "Site ligado na porta interna; publique o nginx (reload) para o domínio responder."
        )[:2000]
    site.status = WebSiteStatus.RUNNING
    order.status = WebOrderStatus.ACTIVE
    order.provision_progress = 100
    order.provision_step = "ready"
    db.commit()
    db.refresh(site)
    return site
