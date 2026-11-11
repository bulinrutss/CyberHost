#!/usr/bin/env python3
"""Atualiza bônus CyberCloud (VPS + web) direto no SQL."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.config import get_settings

VPS = {"basico": 20, "intermediario": 50, "avancado": 100}
WEB = {"web_starter": 20, "web_plus": 50, "web_pro": 100}


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        for slug, gb in VPS.items():
            conn.execute(
                text("UPDATE vps_plan_presets SET cloud_bonus_gb = :gb WHERE slug = :slug"),
                {"gb": gb, "slug": slug},
            )
        # coluna pode não existir ainda em web_plan_presets
        try:
            for slug, gb in WEB.items():
                conn.execute(
                    text("UPDATE web_plan_presets SET cloud_bonus_gb = :gb WHERE slug = :slug"),
                    {"gb": gb, "slug": slug},
                )
        except Exception as exc:
            print("web_plan_presets:", exc)
        vps = conn.execute(
            text("SELECT slug, cloud_bonus_gb FROM vps_plan_presets ORDER BY id")
        ).fetchall()
    print("VPS:")
    for row in vps:
        print(f"  {row[0]}={row[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
