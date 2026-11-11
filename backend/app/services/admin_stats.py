"""Agregados do painel administrativo — pedidos, host, clientes e eventos."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cloud_file import CloudFile
from app.models.cloud_storage_order import CloudStorageOrder
from app.models.game_server import GameOrder, GameServer, GameServerStatus
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder, VpsStatus
from app.services.admin_management import machine_event_can_clear, order_can_hard_delete

COMPLETED = frozenset({"active", "paid"})
PENDING = frozenset({"pending_payment", "provisioning"})
DENIED = frozenset({"cancelled"})
ERROR = frozenset({"failed"})

ALLOWED_DAYS = (7, 30, 90)
EVENT_LIMIT = 120
CLIENT_LIMIT = 40
MACHINE_LIMIT = 80


def status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def classify_order_status(status: str) -> str:
    raw = status_value(status)
    if raw in COMPLETED:
        return "completed"
    if raw in PENDING:
        return "pending"
    if raw in DENIED:
        return "denied"
    if raw in ERROR:
        return "error"
    return "other"


def period_start(days: int, now: datetime | None = None) -> datetime:
    current = now or datetime.utcnow()
    return datetime(current.year, current.month, current.day) - timedelta(days=max(1, days) - 1)


def date_keys(days: int, now: datetime | None = None) -> list[str]:
    start = period_start(days, now).date()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(max(1, days))]


def empty_day() -> dict[str, int]:
    return {
        "completed": 0,
        "pending": 0,
        "denied": 0,
        "error": 0,
        "other": 0,
        "revenue_cents": 0,
        "total": 0,
    }


def build_daily_series(
    days: int,
    rows: Iterable[tuple[datetime | None, str, int]],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    buckets = {key: empty_day() for key in date_keys(days, now)}
    for created_at, status, cents in rows:
        if created_at is None:
            continue
        key = created_at.date().isoformat()
        if key not in buckets:
            continue
        bucket_name = classify_order_status(status)
        buckets[key][bucket_name] = int(buckets[key][bucket_name]) + 1
        buckets[key]["total"] = int(buckets[key]["total"]) + 1
        if bucket_name == "completed":
            buckets[key]["revenue_cents"] = int(buckets[key]["revenue_cents"]) + int(cents or 0)
    return [{"date": key, **buckets[key]} for key in date_keys(days, now)]


def _count_by(values: Iterable[str]) -> dict[str, int]:
    tallies: dict[str, int] = defaultdict(int)
    for value in values:
        tallies[value] += 1
    return dict(tallies)


def collect_admin_stats(db: Session, days: int = 30) -> dict[str, Any]:
    window = days if days in ALLOWED_DAYS else 30
    now = datetime.utcnow()
    since = period_start(window, now)

    users = db.query(User).all()
    customers = [user for user in users if not user.is_admin]
    user_by_id = {user.id: user for user in users}

    instances = (
        db.query(VpsInstance)
        .filter(VpsInstance.status != VpsStatus.DELETED)
        .order_by(VpsInstance.updated_at.desc())
        .all()
    )

    vps_orders = db.query(VpsOrder).filter(VpsOrder.created_at >= since).all()
    cloud_orders = db.query(CloudStorageOrder).filter(CloudStorageOrder.created_at >= since).all()
    game_orders = db.query(GameOrder).filter(GameOrder.created_at >= since).all()
    game_servers = (
        db.query(GameServer)
        .filter(GameServer.status != GameServerStatus.DELETED)
        .all()
    )

    cloud_used = (
        db.query(func.coalesce(func.sum(CloudFile.size_bytes), 0))
        .filter(CloudFile.is_folder.is_(False), CloudFile.upload_status == "ready")
        .scalar()
    )
    cloud_files = (
        db.query(func.count(CloudFile.id))
        .filter(CloudFile.is_folder.is_(False), CloudFile.upload_status == "ready")
        .scalar()
    )

    order_rows: list[dict[str, Any]] = []
    for order in vps_orders:
        order_rows.append(
            {
                "kind": "vps",
                "id": order.id,
                "user_id": order.user_id,
                "status": status_value(order.status),
                "title": {
                    "new": "Nova VPS",
                    "upgrade": "Upgrade de VPS",
                    "renewal": "Renovação de VPS",
                    "admin": "Ajuste da equipe",
                }.get(status_value(order.order_type), "Pedido VPS"),
                "subject": getattr(order, "notes", None) or order.hostname,
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": order.error_message,
                "step": order.provision_step,
            }
        )
    for order in cloud_orders:
        renewal = bool(order.renewal_months)
        order_rows.append(
            {
                "kind": "cloud",
                "id": order.id,
                "user_id": order.user_id,
                "status": status_value(order.status),
                "title": "Ajuste da equipe" if getattr(order, "notes", None) else (
                    "Renovação CyberCloud" if renewal else "Espaço CyberCloud"
                ),
                "subject": getattr(order, "notes", None)
                or (
                    f"{order.renewal_months} mês(es)" if renewal else f"+{order.extra_gb} GB"
                ),
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": None,
                "step": None,
            }
        )
    for order in game_orders:
        order_rows.append(
            {
                "kind": "game",
                "id": order.id,
                "user_id": order.user_id,
                "status": status_value(order.status),
                "title": f"Servidor {status_value(order.game_type)}",
                "subject": order.server_name,
                "total_cents": int(order.total_cents or 0),
                "created_at": order.created_at,
                "error_message": order.error_message,
                "step": order.provision_step,
            }
        )

    classified = [classify_order_status(row["status"]) for row in order_rows]
    order_counts = {
        "total": len(order_rows),
        "completed": classified.count("completed"),
        "pending": classified.count("pending"),
        "denied": classified.count("denied"),
        "error": classified.count("error"),
        "other": classified.count("other"),
        "by_kind": _count_by(row["kind"] for row in order_rows),
        "by_status": _count_by(row["status"] for row in order_rows),
    }
    revenue_cents = sum(
        int(row["total_cents"])
        for row, bucket in zip(order_rows, classified)
        if bucket == "completed"
    )

    vps_statuses = _count_by(status_value(inst.status) for inst in instances)
    allocated_vcpu = sum(int(inst.vcpu or 0) for inst in instances)
    allocated_ram_mb = sum(int(inst.ram_mb or 0) for inst in instances)
    allocated_disk_gb = sum(int(inst.disk_gb or 0) for inst in instances)
    running = vps_statuses.get("running", 0)
    stopped = vps_statuses.get("stopped", 0)
    vps_error = vps_statuses.get("error", 0)
    suspended = sum(1 for inst in instances if inst.suspended_for_billing)

    spend_by_user: dict[int, int] = defaultdict(int)
    orders_by_user: dict[int, int] = defaultdict(int)
    errors_by_user: dict[int, int] = defaultdict(int)
    for row, bucket in zip(order_rows, classified):
        uid = int(row["user_id"])
        orders_by_user[uid] += 1
        if bucket == "completed":
            spend_by_user[uid] += int(row["total_cents"])
        if bucket == "error":
            errors_by_user[uid] += 1

    vps_by_user: dict[int, list[VpsInstance]] = defaultdict(list)
    for inst in instances:
        vps_by_user[inst.user_id].append(inst)

    clients: list[dict[str, Any]] = []
    for user in customers:
        owned = vps_by_user.get(user.id, [])
        clients.append(
            {
                "id": user.id,
                "name": user.name,
                "phone": user.phone,
                "is_active": bool(user.is_active),
                "vps_count": len(owned),
                "vps_running": sum(1 for inst in owned if status_value(inst.status) == "running"),
                "vps_error": sum(1 for inst in owned if status_value(inst.status) == "error"),
                "orders": orders_by_user.get(user.id, 0),
                "spent_cents": spend_by_user.get(user.id, 0),
                "order_errors": errors_by_user.get(user.id, 0),
                "cloud_gb": int(user.cloud_contracted_gb or 0),
                "cloud_suspended": bool(user.cloud_suspended_for_billing),
            }
        )
    clients.sort(key=lambda row: (row["spent_cents"], row["vps_count"], row["orders"]), reverse=True)

    machines: list[dict[str, Any]] = []
    for inst in instances:
        owner = user_by_id.get(inst.user_id)
        machines.append(
            {
                "id": inst.id,
                "vm_name": inst.vm_name,
                "status": status_value(inst.status),
                "vcpu": inst.vcpu,
                "ram_mb": inst.ram_mb,
                "disk_gb": inst.disk_gb,
                "ip_address": inst.ip_address,
                "paid_until": inst.paid_until,
                "suspended_for_billing": bool(inst.suspended_for_billing),
                "error_message": inst.error_message,
                "user_id": inst.user_id,
                "user_name": owner.name if owner else "—",
                "user_phone": owner.phone if owner else "",
            }
        )
    machines.sort(
        key=lambda row: (
            0 if row["status"] == "error" else 1 if row["suspended_for_billing"] else 2,
            row["vm_name"],
        )
    )

    linked_vps_orders = {
        int(inst.order_id) for inst in instances if getattr(inst, "order_id", None)
    }
    linked_game_orders = {
        int(server.order_id) for server in game_servers if getattr(server, "order_id", None)
    }

    events: list[dict[str, Any]] = []
    for row, bucket in zip(order_rows, classified):
        owner = user_by_id.get(int(row["user_id"]))
        level = "info"
        if bucket == "error":
            level = "error"
        elif bucket == "denied":
            level = "warning"
        elif bucket == "pending":
            level = "pending"
        kind = str(row["kind"])
        linked = (kind == "vps" and int(row["id"]) in linked_vps_orders) or (
            kind == "game" and int(row["id"]) in linked_game_orders
        )
        events.append(
            {
                "at": row["created_at"],
                "level": level,
                "source": kind,
                "title": row["title"],
                "subject": row["subject"],
                "status": row["status"],
                "detail": row["error_message"] or row["step"],
                "user_id": row["user_id"],
                "user_name": owner.name if owner else "—",
                "user_phone": owner.phone if owner else "",
                "total_cents": row["total_cents"],
                "order_id": int(row["id"]),
                "can_delete": order_can_hard_delete(kind, row["status"], linked=linked),
            }
        )
    for inst in instances:
        if status_value(inst.status) not in {"error", "creating", "configuring"} and not (
            inst.error_message or inst.suspended_for_billing
        ):
            continue
        owner = user_by_id.get(inst.user_id)
        level = "error" if status_value(inst.status) == "error" or inst.error_message else "warning"
        events.append(
            {
                "at": inst.updated_at or inst.created_at,
                "level": level,
                "source": "machine",
                "title": inst.vm_name,
                "subject": status_value(inst.status),
                "status": status_value(inst.status),
                "detail": inst.error_message
                or ("Suspensa por billing" if inst.suspended_for_billing else None),
                "user_id": inst.user_id,
                "user_name": owner.name if owner else "—",
                "user_phone": owner.phone if owner else "",
                "total_cents": 0,
                "instance_id": inst.id,
                "can_delete": machine_event_can_clear(
                    inst.status,
                    error_message=inst.error_message,
                    suspended=bool(inst.suspended_for_billing),
                ),
            }
        )
    for user in users:
        if not user.cloud_suspended_for_billing:
            continue
        events.append(
            {
                "at": user.cloud_paid_until or user.created_at,
                "level": "warning",
                "source": "cloud",
                "title": "CyberCloud suspenso",
                "subject": user.name,
                "status": "suspended",
                "detail": "Espaço contratado suspenso por billing",
                "user_id": user.id,
                "user_name": user.name,
                "user_phone": user.phone,
                "total_cents": 0,
                "can_delete": False,
            }
        )

    events.sort(key=lambda item: item["at"] or datetime.min, reverse=True)

    daily = build_daily_series(
        window,
        (
            (row["created_at"], row["status"], int(row["total_cents"]))
            for row in order_rows
        ),
        now,
    )

    return {
        "days": window,
        "generated_at": now,
        "clients": {
            "total": len(customers),
            "active": sum(1 for user in customers if user.is_active),
            "admins": sum(1 for user in users if user.is_admin),
        },
        "orders": {**order_counts, "revenue_cents": revenue_cents},
        "host": {
            "vps_total": len(instances),
            "vps_running": running,
            "vps_stopped": stopped,
            "vps_error": vps_error,
            "vps_suspended": suspended,
            "vps_by_status": vps_statuses,
            "allocated_vcpu": allocated_vcpu,
            "allocated_ram_mb": allocated_ram_mb,
            "allocated_disk_gb": allocated_disk_gb,
            "game_servers": len(game_servers),
            "cloud_used_bytes": int(cloud_used or 0),
            "cloud_files": int(cloud_files or 0),
            "cloud_contracted_gb": sum(int(user.cloud_contracted_gb or 0) for user in users),
            "cloud_suspended_users": sum(1 for user in users if user.cloud_suspended_for_billing),
        },
        "daily": daily,
        "top_clients": clients[:CLIENT_LIMIT],
        "machines": machines[:MACHINE_LIMIT],
        "events": events[:EVENT_LIMIT],
    }
