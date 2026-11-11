#!/usr/bin/env python3
"""Regenera nginx e SSL de todos os sites ativos (subdomínios slug.ruts.dev)."""

from __future__ import annotations

from app.database import SessionLocal
from app.models import cloud_storage_order as _cloud_storage_order_models  # noqa: F401
from app.models import coupon as _coupon_models  # noqa: F401
from app.models import game_server as _game_server_models  # noqa: F401
from app.models import vps_connection as _vps_connection_models  # noqa: F401
from app.models import web_site as _web_site_models  # noqa: F401
from app.models.web_site import WebSite, WebSiteStatus
from app.services import web_nginx, web_ssl


def main() -> int:
    db = SessionLocal()
    try:
        sites = (
            db.query(WebSite)
            .filter(WebSite.status != WebSiteStatus.DELETED)
            .order_by(WebSite.id.asc())
            .all()
        )
        if not sites:
            print("nenhum site ativo")
            return 0
        ssl_ok = 0
        for site in sites:
            web_nginx.write_snippet(site)
            host = web_ssl.public_site_host(site) or site.site_slug
            print(f"snippet site={site.id} slug={site.site_slug} host={host}")
        web_nginx.reload_nginx()
        for site in sites:
            if web_ssl.try_enable_https(site)[0]:
                ssl_ok += 1
        web_nginx.reload_nginx()
        print(f"sync concluído: {len(sites)} site(s), {ssl_ok} com SSL")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
