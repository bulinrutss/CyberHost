"""Cota de armazenamento CyberCloud por usuário."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.models.vps import VpsInstance, VpsPlanPreset, VpsStatus
from app.services.billing import get_cloud_billing_snapshot

settings = get_settings()
GB = 1024**3


def account_base_quota_bytes() -> int:
    return int(settings.cloud_files_account_base_quota_gb * GB)


def parse_storage_packages() -> list[dict]:
    raw = settings.cloud_storage_packages.strip()
    if not raw:
        return []
    packages: list[dict] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        gb_str, cents_str = part.split(":", 1)
        gb = int(gb_str.strip())
        packages.append(
            {
                "slug": f"{gb}gb",
                "gb": gb,
                "price_cents": int(cents_str.strip()),
            }
        )
    return packages


def preset_cloud_bonus_gb(db: Session, instance: VpsInstance) -> int:
    if not instance.plan_id:
        return 0
    preset = (
        db.query(VpsPlanPreset)
        .filter(
            VpsPlanPreset.plan_id == instance.plan_id,
            VpsPlanPreset.vcpu == instance.vcpu,
            VpsPlanPreset.ram_mb == instance.ram_mb,
            VpsPlanPreset.disk_gb == instance.disk_gb,
            VpsPlanPreset.is_active.is_(True),
        )
        .first()
    )
    return int(preset.cloud_bonus_gb) if preset else 0


def vps_cloud_bonus_bytes(db: Session, user_id: int) -> int:
    instances = (
        db.query(VpsInstance)
        .filter(
            VpsInstance.user_id == user_id,
            VpsInstance.status != VpsStatus.DELETED,
        )
        .all()
    )
    total_gb = sum(preset_cloud_bonus_gb(db, inst) for inst in instances)
    return total_gb * GB


def web_cloud_bonus_bytes(db: Session, user_id: int) -> int:
    from app.models.web_site import WebOrder, WebPlanPreset, WebSite, WebSiteStatus

    rows = (
        db.query(WebPlanPreset.cloud_bonus_gb)
        .join(WebOrder, WebOrder.preset_id == WebPlanPreset.id)
        .join(WebSite, WebSite.order_id == WebOrder.id)
        .filter(
            WebSite.user_id == user_id,
            WebSite.status != WebSiteStatus.DELETED,
        )
        .all()
    )
    total_gb = sum(int(row[0] or 0) for row in rows)
    return total_gb * GB


def service_cloud_bonus_bytes(db: Session, user_id: int) -> int:
    return vps_cloud_bonus_bytes(db, user_id) + web_cloud_bonus_bytes(db, user_id)


def subscribed_extra_bytes(user: User) -> int:
    contracted_gb = int(getattr(user, "cloud_contracted_gb", 0) or 0)
    if contracted_gb <= 0:
        return 0
    snapshot = get_cloud_billing_snapshot(user)
    if snapshot["billing_state"] == "suspended":
        return 0
    return contracted_gb * GB


def bonus_extra_bytes(user: User) -> int:
    return int(user.cloud_extra_quota_bytes or 0)


def user_quota_bytes(db: Session, user: User) -> int:
    return (
        account_base_quota_bytes()
        + service_cloud_bonus_bytes(db, user.id)
        + subscribed_extra_bytes(user)
        + bonus_extra_bytes(user)
    )


def quota_breakdown(db: Session, user: User) -> dict:
    base = account_base_quota_bytes()
    vps_bonus = vps_cloud_bonus_bytes(db, user.id)
    web_bonus = web_cloud_bonus_bytes(db, user.id)
    service_bonus = vps_bonus + web_bonus
    subscribed = subscribed_extra_bytes(user)
    bonus = bonus_extra_bytes(user)
    extra = subscribed + bonus
    billing = get_cloud_billing_snapshot(user)
    return {
        "base_bytes": base,
        "vps_bonus_bytes": service_bonus,
        "subscribed_bytes": subscribed,
        "bonus_bytes": bonus,
        "extra_bytes": extra,
        "contracted_gb": int(getattr(user, "cloud_contracted_gb", 0) or 0),
        "quota_bytes": base + service_bonus + extra,
        "billing": billing,
    }
