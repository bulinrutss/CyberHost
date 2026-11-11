import asyncio
import logging
from contextlib import asynccontextmanager

from app.console_io import configure_logging, safe_print

configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from app.api import api_router
from app.api_cache_headers import api_no_store_cache
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.database_bootstrap import ensure_mariadb_database
from app.models import console_ticket as _console_ticket_models  # noqa: F401
from app.models import auth_security as _auth_security_models  # noqa: F401
from app.models import billing_reminder as _billing_reminder_models  # noqa: F401
from app.models import cloud_file as _cloud_file_models  # noqa: F401 — registra tabelas
from app.models import cloud_storage_order as _cloud_storage_order_models  # noqa: F401
from app.models import coupon as _coupon_models  # noqa: F401 — registra tabelas
from app.models import game_server as _game_server_models  # noqa: F401 — registra tabelas
from app.models import web_site as _web_site_models  # noqa: F401
from app.models import web_site_analytics as _web_site_analytics_models  # noqa: F401
from app.models import analytics as _analytics_models  # noqa: F401
from app.models import finance as _finance_models  # noqa: F401
from app.models import finance_auth as _finance_auth_models  # noqa: F401
from app.models import finance_user as _finance_user_models  # noqa: F401
from app.finance_database import init_finance_db
from app.models import host_push as _host_push_models  # noqa: F401
from app.models import vps_connection as _vps_connection_models  # noqa: F401
from app.models import nginx_proxy as _nginx_proxy_models  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsPlan, VpsStatus
from app.services.admin_bootstrap import seed_admin_user
from app.services.game_plan_presets import seed_game_plan_presets
from app.services.web_plan_presets import seed_web_plan_presets
from app.services.plan_presets import seed_plan_presets
from app.services.billing import initial_paid_until
from app.services.billing_enforcer import billing_enforcer_loop, enforce_billing_suspensions
from app.services.cloud_discord_purge import discord_purge_loop
from app.services.finance_push import finance_push_loop

settings = get_settings()
logger = logging.getLogger(__name__)


def create_schema() -> None:
    """create_all em 2 workers pode colidir ao criar tabela nova (MySQL 1050)."""
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        orig = exc.orig
        code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
        if code == 1050:
            logger.info("create_all: tabela já criada por outro worker")
            return
        raise


def migrate_db():
    """Adiciona colunas novas em bancos já existentes."""
    inspector = inspect(engine)
    is_sqlite = settings.database_url.startswith("sqlite")

    if not is_sqlite:
        _migrate_billing_columns(inspector)
        _migrate_cloud_quota_columns(inspector)
        _migrate_pix_columns(inspector)
        _migrate_auth_security_columns(inspector)
        _migrate_windows_password_column(inspector)
        _migrate_order_notes_columns(inspector)
        _migrate_instance_order_fk_nullable(inspector)
        _migrate_finance_receipt_column(inspector)
        _migrate_finance_goal_columns(inspector)
        _migrate_web_site_columns(inspector)
        return
    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "is_admin" not in user_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
                )

    if "vps_orders" in inspector.get_table_names():
        order_cols = {c["name"] for c in inspector.get_columns("vps_orders")}
        if "provision_progress" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vps_orders ADD COLUMN provision_progress INTEGER NOT NULL DEFAULT 0"
                    )
                )
        if "provision_step" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_orders ADD COLUMN provision_step VARCHAR(40)")
                )
        if "order_type" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_orders ADD COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'new'")
                )
        if "target_instance_id" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_orders ADD COLUMN target_instance_id INTEGER")
                )
        if "disk_gb" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_orders ADD COLUMN disk_gb INTEGER NOT NULL DEFAULT 70")
                )
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE vps_orders SET order_type = 'new' WHERE order_type IN ('NEW', '') OR order_type IS NULL")
            )
            conn.execute(
                text("UPDATE vps_orders SET order_type = 'upgrade' WHERE order_type = 'UPGRADE'")
            )

    if "vps_plans" in inspector.get_table_names():
        plan_cols = {c["name"] for c in inspector.get_columns("vps_plans")}
        for col, ddl in [
            ("slug", "ALTER TABLE vps_plans ADD COLUMN slug VARCHAR(32) NOT NULL DEFAULT 'vps'"),
            ("network_mbps", "ALTER TABLE vps_plans ADD COLUMN network_mbps INTEGER NOT NULL DEFAULT 100"),
            ("default_disk_gb", "ALTER TABLE vps_plans ADD COLUMN default_disk_gb INTEGER NOT NULL DEFAULT 70"),
            ("max_disk_gb", "ALTER TABLE vps_plans ADD COLUMN max_disk_gb INTEGER NOT NULL DEFAULT 500"),
            ("price_per_gb_disk_cents", "ALTER TABLE vps_plans ADD COLUMN price_per_gb_disk_cents INTEGER NOT NULL DEFAULT 150"),
            ("monthly_base_cents", "ALTER TABLE vps_plans ADD COLUMN monthly_base_cents INTEGER NOT NULL DEFAULT 0"),
        ]:
            if col not in plan_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))

    _migrate_billing_columns(inspector)
    _migrate_cloud_quota_columns(inspector)
    _migrate_pix_columns(inspector)
    _migrate_auth_security_columns(inspector)
    _migrate_windows_password_column(inspector)
    _migrate_order_notes_columns(inspector)
    _migrate_instance_order_fk_nullable(inspector)
    _migrate_finance_receipt_column(inspector)
    _migrate_finance_goal_columns(inspector)


def _migrate_instance_order_fk_nullable(inspector) -> None:
    """Permite apagar o pedido original sem derrubar a VPS/game."""
    if settings.database_url.startswith("sqlite"):
        return
    for table, ddl in (
        ("vps_instances", "ALTER TABLE vps_instances MODIFY COLUMN order_id INTEGER NULL"),
        ("game_servers", "ALTER TABLE game_servers MODIFY COLUMN order_id INTEGER NULL"),
    ):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"]: c for c in inspector.get_columns(table)}
        info = cols.get("order_id")
        if info is None or info.get("nullable"):
            continue
        with engine.begin() as conn:
            conn.execute(text(ddl))


def _migrate_order_type_enum(inspector) -> None:
    """ENUM antigo só tinha new/upgrade; renovação exige 'renewal'."""
    if "vps_orders" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("vps_orders")}
    if "order_type" not in cols:
        return
    type_str = str(cols["order_type"]["type"]).lower()
    if "enum" not in type_str or "renewal" in type_str:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE vps_orders MODIFY COLUMN order_type "
                "VARCHAR(20) NOT NULL DEFAULT 'new'"
            )
        )
        conn.execute(
            text(
                "UPDATE vps_orders SET order_type = 'new' "
                "WHERE order_type IN ('NEW', '') OR order_type IS NULL"
            )
        )
        conn.execute(
            text("UPDATE vps_orders SET order_type = 'upgrade' WHERE order_type = 'UPGRADE'")
        )


def _migrate_billing_columns(inspector) -> None:
    if "vps_plans" in inspector.get_table_names():
        plan_cols = {c["name"] for c in inspector.get_columns("vps_plans")}
        if "monthly_base_cents" not in plan_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vps_plans ADD COLUMN monthly_base_cents INTEGER NOT NULL DEFAULT 0"
                    )
                )

    if "vps_instances" in inspector.get_table_names():
        inst_cols = {c["name"] for c in inspector.get_columns("vps_instances")}
        for col, ddl in [
            ("plan_id", "ALTER TABLE vps_instances ADD COLUMN plan_id INTEGER"),
            ("disk_gb", "ALTER TABLE vps_instances ADD COLUMN disk_gb INTEGER NOT NULL DEFAULT 70"),
            ("network_mbps", "ALTER TABLE vps_instances ADD COLUMN network_mbps INTEGER NOT NULL DEFAULT 100"),
            ("paid_until", "ALTER TABLE vps_instances ADD COLUMN paid_until DATETIME"),
            ("billing_day", "ALTER TABLE vps_instances ADD COLUMN billing_day INTEGER NOT NULL DEFAULT 1"),
            (
                "suspended_for_billing",
                "ALTER TABLE vps_instances ADD COLUMN suspended_for_billing BOOLEAN NOT NULL DEFAULT 0",
            ),
        ]:
            if col not in inst_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))

    if "vps_orders" in inspector.get_table_names():
        order_cols = {c["name"] for c in inspector.get_columns("vps_orders")}
        if "renewal_months" not in order_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE vps_orders ADD COLUMN renewal_months INTEGER"))
        if "upgrade_monthly_delta_cents" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_orders ADD COLUMN upgrade_monthly_delta_cents INTEGER")
                )
        for col, ddl in [
            ("coupon_id", "ALTER TABLE vps_orders ADD COLUMN coupon_id INTEGER"),
            ("subtotal_cents", "ALTER TABLE vps_orders ADD COLUMN subtotal_cents INTEGER"),
            ("discount_cents", "ALTER TABLE vps_orders ADD COLUMN discount_cents INTEGER NOT NULL DEFAULT 0"),
            ("os_template", "ALTER TABLE vps_orders ADD COLUMN os_template VARCHAR(20) NOT NULL DEFAULT 'sv2016'"),
        ]:
            if col not in order_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
        _migrate_order_type_enum(inspector)

    if "vps_instances" in inspector.get_table_names():
        inst_cols = {c["name"] for c in inspector.get_columns("vps_instances")}
        if "os_template" not in inst_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vps_instances ADD COLUMN os_template VARCHAR(20) NOT NULL DEFAULT 'sv2016'"
                    )
                )

    if "cloud_file_chunks" in inspector.get_table_names():
        chunk_cols = {c["name"] for c in inspector.get_columns("cloud_file_chunks")}
        if "discord_attachment_id" not in chunk_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE cloud_file_chunks ADD COLUMN discord_attachment_id VARCHAR(64)"
                    )
                )
        if "discord_attachment_url" not in chunk_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cloud_file_chunks ADD COLUMN discord_attachment_url TEXT"))
        if "discord_url_cached_at" not in chunk_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE cloud_file_chunks ADD COLUMN discord_url_cached_at DATETIME")
                )
        if "discord_bot_index" not in chunk_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE cloud_file_chunks ADD COLUMN discord_bot_index INTEGER")
                )


def _migrate_cloud_quota_columns(inspector) -> None:
    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "cloud_extra_quota_bytes" not in user_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN cloud_extra_quota_bytes BIGINT NOT NULL DEFAULT 0"
                    )
                )
        else:
            col = next(
                c for c in inspector.get_columns("users") if c["name"] == "cloud_extra_quota_bytes"
            )
            col_type = str(col.get("type", "")).upper()
            if "BIGINT" not in col_type:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE users MODIFY COLUMN cloud_extra_quota_bytes "
                            "BIGINT NOT NULL DEFAULT 0"
                        )
                    )

    if "vps_plan_presets" in inspector.get_table_names():
        preset_cols = {c["name"] for c in inspector.get_columns("vps_plan_presets")}
        if "cloud_bonus_gb" not in preset_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vps_plan_presets ADD COLUMN cloud_bonus_gb INTEGER NOT NULL DEFAULT 0"
                    )
                )

    if "web_plan_presets" in inspector.get_table_names():
        web_preset_cols = {c["name"] for c in inspector.get_columns("web_plan_presets")}
        if "cloud_bonus_gb" not in web_preset_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE web_plan_presets ADD COLUMN cloud_bonus_gb INTEGER NOT NULL DEFAULT 0"
                    )
                )

    if "vps_instances" in inspector.get_table_names():
        inst_cols = {c["name"] for c in inspector.get_columns("vps_instances")}
        if "admin_pending_charge_cents" not in inst_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vps_instances ADD COLUMN admin_pending_charge_cents "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
        if "custom_monthly_cents" not in inst_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE vps_instances ADD COLUMN custom_monthly_cents INTEGER NULL")
                )

    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "admin_pending_cloud_charge_cents" not in user_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN admin_pending_cloud_charge_cents "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
        cloud_billing_cols = {
            "cloud_contracted_gb": "INTEGER NOT NULL DEFAULT 0",
            "cloud_paid_until": "DATETIME NULL",
            "cloud_billing_day": "INTEGER NOT NULL DEFAULT 1",
            "cloud_monthly_cents": "INTEGER NOT NULL DEFAULT 0",
            "cloud_suspended_for_billing": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for col, ddl in cloud_billing_cols.items():
            if col not in user_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))

    if "cloud_storage_orders" in inspector.get_table_names():
        order_cols = {c["name"] for c in inspector.get_columns("cloud_storage_orders")}
        if "renewal_months" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE cloud_storage_orders ADD COLUMN renewal_months INTEGER NULL")
                )


def _migrate_pix_columns(inspector) -> None:
    pix_cols = [
        ("pix_br_code", "TEXT"),
        ("pix_qr_base64", "TEXT"),
        ("pix_expires_at", "DATETIME"),
    ]
    for table in ("vps_orders", "game_orders", "cloud_storage_orders", "web_orders"):
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for col, ddl in pix_cols:
            if col not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _migrate_web_site_columns(inspector) -> None:
    if "web_orders" in inspector.get_table_names():
        order_cols = {c["name"] for c in inspector.get_columns("web_orders")}
        if "site_slug" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE web_orders ADD COLUMN site_slug VARCHAR(63) NOT NULL DEFAULT ''")
                )
        domain_col = next(
            (c for c in inspector.get_columns("web_orders") if c["name"] == "domain"),
            None,
        )
        if domain_col and not domain_col.get("nullable", True):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE web_orders MODIFY COLUMN domain VARCHAR(253) NULL"))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE web_orders SET site_slug = CONCAT('site-', id) "
                    "WHERE site_slug IS NULL OR site_slug = ''"
                )
            )
        if "coupon_id" not in order_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE web_orders ADD COLUMN coupon_id INTEGER"))
        if "subtotal_cents" not in order_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE web_orders ADD COLUMN subtotal_cents INTEGER"))
        if "discount_cents" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE web_orders ADD COLUMN discount_cents INTEGER NOT NULL DEFAULT 0")
                )
        if "order_type" not in order_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE web_orders ADD COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'new'"
                    )
                )
        if "target_site_id" not in order_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE web_orders ADD COLUMN target_site_id INTEGER NULL"))
        if "renewal_months" not in order_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE web_orders ADD COLUMN renewal_months INTEGER NULL"))

    if "coupon_redemptions" in inspector.get_table_names():
        redemption_cols = {c["name"] for c in inspector.get_columns("coupon_redemptions")}
        order_id_col = next(
            (c for c in inspector.get_columns("coupon_redemptions") if c["name"] == "order_id"),
            None,
        )
        if order_id_col and not order_id_col.get("nullable", True):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE coupon_redemptions MODIFY COLUMN order_id INTEGER NULL"))
        if "web_order_id" not in redemption_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE coupon_redemptions ADD COLUMN web_order_id INTEGER UNIQUE"))

    if "web_sites" not in inspector.get_table_names():
        return
    site_cols = {c["name"] for c in inspector.get_columns("web_sites")}
    if "site_slug" not in site_cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE web_sites ADD COLUMN site_slug VARCHAR(63) NOT NULL DEFAULT ''")
            )
    domain_col = next(
        (c for c in inspector.get_columns("web_sites") if c["name"] == "domain"),
        None,
    )
    if domain_col and not domain_col.get("nullable", True):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE web_sites MODIFY COLUMN domain VARCHAR(253) NULL"))
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE web_sites SET site_slug = CONCAT('site-', id) "
                "WHERE site_slug IS NULL OR site_slug = ''"
            )
        )
        conn.execute(
            text(
                "UPDATE web_sites SET domain = NULL "
                "WHERE domain IS NOT NULL AND TRIM(domain) = ''"
            )
        )


def _migrate_auth_security_columns(inspector) -> None:
    if "users" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("users")}
    if "mfa_secret" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(255)"))
    if "mfa_enabled" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT 0")
            )
    if "email" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
            try:
                if settings.database_url.startswith("sqlite"):
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
                        )
                    )
                else:
                    conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
            except OperationalError as exc:
                orig = exc.orig
                code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
                if code not in (1061,):
                    raise


def _migrate_windows_password_column(inspector) -> None:
    if "vps_instances" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("vps_instances")}
    col = cols.get("windows_admin_password")
    if col is None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE vps_instances ADD COLUMN windows_admin_password VARCHAR(512)"
                )
            )
        return
    length = getattr(col["type"], "length", None)
    type_str = str(col["type"]).upper()
    if (length is not None and length >= 512) or "512" in type_str or "TEXT" in type_str:
        return
    if settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE vps_instances MODIFY COLUMN windows_admin_password VARCHAR(512)"
            )
        )


def _migrate_order_notes_columns(inspector) -> None:
    for table in ("vps_orders", "cloud_storage_orders"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "notes" not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN notes TEXT"))


def _migrate_finance_receipt_column(inspector) -> None:
    if "finance_transactions" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("finance_transactions")}
    if "receipt_ext" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE finance_transactions ADD COLUMN receipt_ext VARCHAR(8)"))


def _migrate_finance_goal_columns(inspector) -> None:
    if "finance_goals" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("finance_goals")}
    statements: list[str] = []
    if "kind" not in cols:
        statements.append(
            "ALTER TABLE finance_goals ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'savings'"
        )
    if "due_day" not in cols:
        statements.append("ALTER TABLE finance_goals ADD COLUMN due_day INTEGER")
    if "period_year" not in cols:
        statements.append("ALTER TABLE finance_goals ADD COLUMN period_year INTEGER")
    if "period_month" not in cols:
        statements.append("ALTER TABLE finance_goals ADD COLUMN period_month INTEGER")
    if not statements:
        return
    with engine.begin() as conn:
        for ddl in statements:
            conn.execute(text(ddl))


def _seal_legacy_guest_passwords() -> None:
    db = SessionLocal()
    try:
        from app.services.guest_secrets import seal_legacy_windows_passwords

        seal_legacy_windows_passwords(db)
    finally:
        db.close()


def backfill_cloud_subscriptions():
    """Migra espaço extra permanente antigo para assinatura mensal."""
    from app.models.user import User
    from app.services.billing import initial_paid_until, user_cloud_billing_anchor
    from app.services.cloud_quota import GB, parse_storage_packages

    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.cloud_extra_quota_bytes > 0, User.cloud_contracted_gb == 0)
            .all()
        )
        if not users:
            return

        packages = parse_storage_packages()

        def monthly_for_gb(gb: int) -> int:
            if not packages:
                return 0
            pkg = next((p for p in packages if p["gb"] == gb), None)
            if pkg:
                return pkg["price_cents"]
            ref = packages[0]
            return int(round(ref["price_cents"] / ref["gb"] * gb))

        for user in users:
            gb = int(user.cloud_extra_quota_bytes // GB)
            if gb <= 0:
                continue
            user.cloud_contracted_gb = gb
            user.cloud_monthly_cents = monthly_for_gb(gb)
            anchor_until, anchor_day = user_cloud_billing_anchor(db, user.id)
            if anchor_until:
                user.cloud_paid_until = anchor_until
                user.cloud_billing_day = anchor_day
            else:
                paid_until, billing_day = initial_paid_until()
                user.cloud_paid_until = paid_until
                user.cloud_billing_day = billing_day
            user.cloud_extra_quota_bytes = 0
            user.cloud_suspended_for_billing = False

        db.commit()
    finally:
        db.close()


def backfill_billing_dates():
    db = SessionLocal()
    try:
        instances = (
            db.query(VpsInstance)
            .filter(
                VpsInstance.paid_until.is_(None),
                VpsInstance.status != VpsStatus.DELETED,
            )
            .all()
        )
        for instance in instances:
            paid_until, billing_day = initial_paid_until(instance.created_at)
            instance.paid_until = paid_until
            instance.billing_day = billing_day
            instance.suspended_for_billing = False
        if instances:
            db.commit()
    finally:
        db.close()


def seed_default_plan():
    db = SessionLocal()
    try:
        plans = [
            VpsPlan(
                slug="vps",
                name="VPS",
                description="NVMe SSD, Xeon E5, 300 Mb/s dedicado. Windows Server com 30 GB incluídos.",
                min_vcpu=2,
                max_vcpu=12,
                min_ram_mb=2048,
                max_ram_mb=12288,
                network_mbps=300,
                default_disk_gb=30,
                max_disk_gb=200,
                monthly_base_cents=0,
                price_per_vcpu_cents=800,
                price_per_gb_ram_cents=800,
                price_per_gb_disk_cents=100,
            ),
            VpsPlan(
                slug="semi_dedicated",
                name="Semi-dedicado",
                description="Mais disco e rede 500 Mb/s dedicada. Windows Server com 30 GB incluídos.",
                min_vcpu=8,
                max_vcpu=24,
                min_ram_mb=8192,
                max_ram_mb=32768,
                network_mbps=500,
                default_disk_gb=30,
                max_disk_gb=500,
                monthly_base_cents=0,
                price_per_vcpu_cents=800,
                price_per_gb_ram_cents=800,
                price_per_gb_disk_cents=100,
            ),
        ]
        if db.query(VpsPlan).count() == 0:
            db.add_all(plans)
            db.commit()
        else:
            for plan_def in plans:
                existing = db.query(VpsPlan).filter(VpsPlan.slug == plan_def.slug).first()
                if existing:
                    existing.name = plan_def.name
                    existing.description = plan_def.description
                    existing.min_vcpu = plan_def.min_vcpu
                    existing.max_vcpu = plan_def.max_vcpu
                    existing.min_ram_mb = plan_def.min_ram_mb
                    existing.max_ram_mb = plan_def.max_ram_mb
                    existing.network_mbps = plan_def.network_mbps
                    existing.default_disk_gb = plan_def.default_disk_gb
                    existing.max_disk_gb = plan_def.max_disk_gb
                    existing.monthly_base_cents = plan_def.monthly_base_cents
                    existing.price_per_vcpu_cents = plan_def.price_per_vcpu_cents
                    existing.price_per_gb_ram_cents = plan_def.price_per_gb_ram_cents
                    existing.price_per_gb_disk_cents = plan_def.price_per_gb_disk_cents
                    existing.is_active = True
                else:
                    db.add(plan_def)
            legacy = db.query(VpsPlan).filter(VpsPlan.slug == "vps").count()
            if legacy == 0:
                first = db.query(VpsPlan).order_by(VpsPlan.id).first()
                if first:
                    first.slug = "vps"
                    first.name = plans[0].name
                    first.description = plans[0].description
                    first.max_vcpu = 12
                    first.min_vcpu = 2
                    first.min_ram_mb = 2048
                    first.max_ram_mb = 12288
                    first.network_mbps = 300
                    first.default_disk_gb = 30
                    first.max_disk_gb = 200
                    first.monthly_base_cents = 0
                    first.price_per_vcpu_cents = 800
                    first.price_per_gb_ram_cents = 800
                    first.price_per_gb_disk_cents = 100
            db.query(VpsInstance).filter(VpsInstance.disk_gb == 0).update({"disk_gb": 30})
            db.commit()
        seed_plan_presets(db)
    finally:
        db.close()


def seed_game_hosts():
    from app.models.game_server import GameHost

    db = SessionLocal()
    try:
        if db.query(GameHost).count() == 0:
            db.add(
                GameHost(
                    name="Host principal",
                    public_ip=settings.game_host_public_ip,
                    data_path=settings.game_servers_data_path,
                    port_range_start=settings.game_port_range_start,
                    port_range_end=settings.game_port_range_end,
                    max_servers=settings.game_host_max_servers,
                    is_active=True,
                )
            )
            db.commit()
        seed_game_plan_presets(db)
    finally:
        db.close()


def seed_web_hosting():
    db = SessionLocal()
    try:
        seed_web_plan_presets(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_mariadb_database()
    create_schema()
    init_finance_db()
    migrate_db()
    _seal_legacy_guest_passwords()
    backfill_billing_dates()
    backfill_cloud_subscriptions()
    seed_admin_user()
    seed_default_plan()
    if settings.game_servers_enabled:
        seed_game_hosts()
    if settings.web_hosting_enabled:
        seed_web_hosting()
    enforce_billing_suspensions()
    configure_logging()
    backend = settings.cloud_files_storage_backend.strip().lower()
    safe_print(f"[CloudFiles] INFO Backend de arquivos: {backend}")
    safe_print("[CloudFiles] INFO Compra de espaco: credito via webhook/sync autenticado")
    upload_gb = get_settings().cloud_files_max_upload_bytes / (1024**3)
    safe_print(
        f"[CloudFiles] INFO Limite por arquivo: {upload_gb:.1f} GB "
        f"({get_settings().cloud_files_max_upload_bytes} bytes)"
    )
    bw = settings.cloud_files_bandwidth_limit_mbps
    if bw > 0:
        safe_print(
            f"[CloudFiles] INFO Limite de banda: {bw:g} Mbps "
            f"(~{bw * 1_000_000 / 8 / 1_024 / 1_024:.1f} MB/s) — upload, Discord e download"
        )
    if backend == "discord":
        if settings.discord_storage_enabled:
            bot_count = len(settings.discord_bot_token_list)
            safe_print(
                f"[CloudFiles] INFO Discord OK — {bot_count} bot(s), "
                f"canal {settings.discord_storage_channel_id}, "
                f"intervalo {settings.discord_upload_interval_seconds}s"
            )
            from app.services.discord_storage import get_discord_storage

            get_discord_storage().refresh_health_async()
        else:
            safe_print(
                "[CloudFiles] WARN CLOUD_FILES_STORAGE_BACKEND=discord mas tokens/canal "
                "Discord não configurados — uploads vão falhar"
            )
    safe_print("[CloudFiles] INFO Logs de upload/download ativos no console")
    enforcer_task = asyncio.create_task(billing_enforcer_loop())
    purge_task = asyncio.create_task(discord_purge_loop())
    push_task = asyncio.create_task(finance_push_loop())
    yield
    enforcer_task.cancel()
    purge_task.cancel()
    push_task.cancel()
    for task in (enforcer_task, purge_task, push_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    description="Painel de automação de VPS",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Step-Up-Required"],
)


@app.middleware("http")
async def api_no_store_cache_middleware(request: Request, call_next):
    return await api_no_store_cache(request, call_next)


@app.middleware("http")
async def cloud_files_access_log(request: Request, call_next):
    path = request.url.path
    is_cloud = path.startswith("/api/files")
    if is_cloud:
        client = request.client.host if request.client else "?"
        safe_print(
            f"[CloudFiles] INFO --> {request.method} {path} "
            f"client={client} query={request.url.query or '-'}"
        )
        logging.getLogger("uvicorn.error").info(
            f"[CloudFiles] --> {request.method} {path}"
        )
    try:
        response = await call_next(request)
    except Exception as exc:
        if is_cloud:
            safe_print(f"[CloudFiles] ERROR EXCEÇÃO {request.method} {path}: {exc}")
            logging.getLogger("uvicorn.error").exception(
                f"[CloudFiles] EXCEÇÃO {request.method} {path}"
            )
        raise
    if is_cloud:
        safe_print(
            f"[CloudFiles] INFO <-- {request.method} {path} status={response.status_code}"
        )
        logging.getLogger("uvicorn.error").info(
            f"[CloudFiles] <-- {request.method} {path} {response.status_code}"
        )
    return response


app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "vmware_docs": "Veja docs/VMWARE_INTEGRATION.md no repositório",
    }
