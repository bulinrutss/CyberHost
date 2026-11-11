"""Planos de hospedagem de site."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.web_site import WebOrder, WebPlanPreset, WebSite

WEB_PRESETS = [
    {
        "slug": "web_starter",
        "name": "Starter",
        "ram_mb": 256,
        "disk_mb": 1024,
        "cpu_percent": 10,
        "php_enabled": False,
        "price_cents": 299,
        "cloud_bonus_gb": 20,
        "sort_order": 1,
    },
    {
        "slug": "web_plus",
        "name": "Plus",
        "ram_mb": 512,
        "disk_mb": 1024,
        "cpu_percent": 25,
        "php_enabled": False,
        "price_cents": 499,
        "cloud_bonus_gb": 50,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "slug": "web_pro",
        "name": "Pro",
        "ram_mb": 1024,
        "disk_mb": 2048,
        "cpu_percent": 50,
        "php_enabled": True,
        "price_cents": 999,
        "cloud_bonus_gb": 100,
        "sort_order": 3,
    },
]


def seed_web_plan_presets(db: Session) -> None:
    for item in WEB_PRESETS:
        row = db.query(WebPlanPreset).filter(WebPlanPreset.slug == item["slug"]).first()
        if row:
            row.name = item["name"]
            row.ram_mb = item["ram_mb"]
            row.disk_mb = item["disk_mb"]
            row.cpu_percent = item["cpu_percent"]
            row.php_enabled = item["php_enabled"]
            row.price_cents = item["price_cents"]
            row.cloud_bonus_gb = item.get("cloud_bonus_gb", 0)
            row.is_popular = item.get("is_popular", False)
            row.sort_order = item.get("sort_order", 0)
            row.is_active = True
        else:
            db.add(WebPlanPreset(**item, is_active=True))
    plus = db.query(WebPlanPreset).filter(WebPlanPreset.slug == "web_plus").first()
    if plus and not plus.php_enabled:
        db.query(WebOrder).filter(WebOrder.preset_id == plus.id).update(
            {WebOrder.php_enabled: False},
            synchronize_session=False,
        )
        plus_site_ids = [
            row[0]
            for row in db.query(WebSite.id)
            .join(WebOrder, WebSite.order_id == WebOrder.id)
            .filter(WebOrder.preset_id == plus.id)
            .all()
        ]
        if plus_site_ids:
            db.query(WebSite).filter(WebSite.id.in_(plus_site_ids)).update(
                {WebSite.php_enabled: False},
                synchronize_session=False,
            )
    db.commit()


def list_presets(db: Session) -> list[WebPlanPreset]:
    return (
        db.query(WebPlanPreset)
        .filter(WebPlanPreset.is_active.is_(True))
        .order_by(WebPlanPreset.sort_order, WebPlanPreset.id)
        .all()
    )


def get_preset(db: Session, preset_id: int) -> WebPlanPreset | None:
    return (
        db.query(WebPlanPreset)
        .filter(WebPlanPreset.id == preset_id, WebPlanPreset.is_active.is_(True))
        .first()
    )
