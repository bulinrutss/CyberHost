#!/usr/bin/env python3
"""Emite/renova HTTPS para um site (uso operacional)."""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.models.web_site import WebSite
from app.services import web_ssl


def main() -> int:
    site_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if site_id <= 0:
        print("uso: enable_web_ssl.py <site_id>", file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        site = db.query(WebSite).filter(WebSite.id == site_id).first()
        if not site:
            print(f"site {site_id} não encontrado", file=sys.stderr)
            return 1
        ok = web_ssl.configure_domain(site)
        print(f"site={site_id} domain={site.domain!r} ssl_active={ok}")
        return 0 if ok else 3
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
