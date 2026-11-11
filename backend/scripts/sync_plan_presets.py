#!/usr/bin/env python3
"""Sincroniza presets VPS no banco (uso operacional)."""

from __future__ import annotations

import app.models  # noqa: F401 — registra todos os mappers

from app.database import SessionLocal
from app.services.plan_presets import seed_plan_presets
from app.models.vps import VpsPlanPreset


def main() -> int:
    db = SessionLocal()
    try:
        seed_plan_presets(db)
        rows = db.query(VpsPlanPreset).order_by(VpsPlanPreset.id).all()
        for row in rows:
            print(f"{row.id} {row.slug} cloud_bonus_gb={row.cloud_bonus_gb}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
