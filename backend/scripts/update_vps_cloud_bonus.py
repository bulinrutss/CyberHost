#!/usr/bin/env python3
"""Atualiza cloud_bonus_gb dos presets VPS (sem carregar ORM User)."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.config import get_settings

UPDATES = {
    "basico": 20,
    "intermediario": 50,
    "avancado": 100,
}


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        for slug, gb in UPDATES.items():
            conn.execute(
                text("UPDATE vps_plan_presets SET cloud_bonus_gb = :gb WHERE slug = :slug"),
                {"gb": gb, "slug": slug},
            )
        rows = conn.execute(
            text("SELECT slug, cloud_bonus_gb FROM vps_plan_presets ORDER BY id")
        ).fetchall()
    for slug, gb in rows:
        print(f"{slug}={gb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
