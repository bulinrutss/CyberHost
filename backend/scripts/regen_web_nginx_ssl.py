#!/usr/bin/env python3
"""Regenera snippet nginx e tenta HTTPS sem banco (uso operacional)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.config import get_settings
from app.services import web_nginx, web_ssl


def main() -> int:
    if len(sys.argv) < 4:
        print("uso: regen_web_nginx_ssl.py <site_id> <slug> <domain> <port>", file=sys.stderr)
        return 2
    site_id = int(sys.argv[1])
    slug = sys.argv[2]
    domain = sys.argv[3]
    port = int(sys.argv[4])
    site = SimpleNamespace(id=site_id, site_slug=slug, domain=domain, port=port)
    settings = get_settings()
    web_nginx.write_domain_snippet(site, settings)
    web_nginx.reload_nginx(settings)
    ok, _err = web_ssl.try_enable_https(site, settings)
    print(f"site={site_id} domain={domain} ssl_active={ok}")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
