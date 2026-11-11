"""Seed e consulta de planos predefinidos."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.vps import VpsPlan, VpsPlanPreset
from app.services.pricing import compute_monthly_price

VPS_PRESETS = [
    {
        "slug": "basico",
        "name": "VPS Starter",
        "vcpu": 2,
        "ram_mb": 2048,
        "disk_gb": 40,
        "cloud_bonus_gb": 20,
        "price_cents": 4990,
        "sort_order": 1,
    },
    {
        "slug": "intermediario",
        "name": "VPS Gamer",
        "vcpu": 4,
        "ram_mb": 4096,
        "disk_gb": 60,
        "cloud_bonus_gb": 50,
        "price_cents": 7490,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "slug": "avancado",
        "name": "VPS Cidade",
        "vcpu": 6,
        "ram_mb": 6144,
        "disk_gb": 70,
        "cloud_bonus_gb": 100,
        "price_cents": 9990,
        "sort_order": 3,
    },
    {
        "slug": "performance",
        "name": "VPS Pro",
        "vcpu": 8,
        "ram_mb": 8192,
        "disk_gb": 80,
        "cloud_bonus_gb": 200,
        "price_cents": 12490,
        "sort_order": 4,
    },
    {
        "slug": "global",
        "name": "VPS Max",
        "vcpu": 12,
        "ram_mb": 12288,
        "disk_gb": 100,
        "cloud_bonus_gb": 350,
        "price_cents": 16990,
        "sort_order": 5,
    },
]

# Semi precisa ficar acima da VPS na mesma spec: pacote VPS + disco extra +
# prêmio da rede 500 Mb/s. Senão o personalizado 8/8/120 (Pro + 40 GB) sai
# mais caro que o Starter Semi.
SEMI_PRESETS = [
    {
        "slug": "sd_basico",
        "name": "Semi Starter",
        "vcpu": 8,
        "ram_mb": 8192,
        "disk_gb": 120,
        "cloud_bonus_gb": 280,
        "price_cents": 17990,
        "sort_order": 1,
    },
    {
        "slug": "sd_intermediario",
        "name": "Semi Gamer",
        "vcpu": 12,
        "ram_mb": 12288,
        "disk_gb": 160,
        "cloud_bonus_gb": 450,
        "price_cents": 24990,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "slug": "sd_avancado",
        "name": "Semi Pro",
        "vcpu": 16,
        "ram_mb": 16384,
        "disk_gb": 200,
        "cloud_bonus_gb": 600,
        "price_cents": 32990,
        "sort_order": 3,
    },
    {
        "slug": "sd_performance",
        "name": "Semi Max",
        "vcpu": 24,
        "ram_mb": 24576,
        "disk_gb": 280,
        "cloud_bonus_gb": 850,
        "price_cents": 42990,
        "sort_order": 4,
    },
]


def seed_plan_presets(db: Session) -> None:
    for plan_slug, presets in (("vps", VPS_PRESETS), ("semi_dedicated", SEMI_PRESETS)):
        plan = db.query(VpsPlan).filter(VpsPlan.slug == plan_slug).first()
        if not plan:
            continue
        for preset_def in presets:
            price_cents = preset_def.get("price_cents")
            if price_cents is None:
                price_cents = compute_monthly_price(
                    plan,
                    preset_def["vcpu"],
                    preset_def["ram_mb"],
                    preset_def["disk_gb"],
                )
            existing = (
                db.query(VpsPlanPreset)
                .filter(VpsPlanPreset.plan_id == plan.id, VpsPlanPreset.slug == preset_def["slug"])
                .first()
            )
            if existing:
                existing.name = preset_def["name"]
                existing.vcpu = preset_def["vcpu"]
                existing.ram_mb = preset_def["ram_mb"]
                existing.disk_gb = preset_def["disk_gb"]
                existing.cloud_bonus_gb = preset_def.get("cloud_bonus_gb", 0)
                existing.price_cents = price_cents
                existing.is_popular = preset_def.get("is_popular", False)
                existing.sort_order = preset_def["sort_order"]
                existing.is_active = True
            else:
                db.add(
                    VpsPlanPreset(
                        plan_id=plan.id,
                        slug=preset_def["slug"],
                        name=preset_def["name"],
                        vcpu=preset_def["vcpu"],
                        ram_mb=preset_def["ram_mb"],
                        disk_gb=preset_def["disk_gb"],
                        cloud_bonus_gb=preset_def.get("cloud_bonus_gb", 0),
                        price_cents=price_cents,
                        is_popular=preset_def.get("is_popular", False),
                        sort_order=preset_def["sort_order"],
                    )
                )
        active_slugs = {p["slug"] for p in presets}
        legacy = (
            db.query(VpsPlanPreset)
            .filter(VpsPlanPreset.plan_id == plan.id, VpsPlanPreset.slug.notin_(active_slugs))
            .all()
        )
        for old in legacy:
            old.is_active = False
    db.commit()


def get_preset(db: Session, preset_id: int, plan_id: int | None = None) -> VpsPlanPreset | None:
    query = db.query(VpsPlanPreset).filter(
        VpsPlanPreset.id == preset_id,
        VpsPlanPreset.is_active.is_(True),
    )
    if plan_id is not None:
        query = query.filter(VpsPlanPreset.plan_id == plan_id)
    return query.first()


def list_plan_presets(db: Session, plan_id: int) -> list[VpsPlanPreset]:
    return (
        db.query(VpsPlanPreset)
        .filter(VpsPlanPreset.plan_id == plan_id, VpsPlanPreset.is_active.is_(True))
        .order_by(VpsPlanPreset.sort_order)
        .all()
    )
