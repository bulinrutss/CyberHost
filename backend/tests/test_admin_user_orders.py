import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.cloud_storage_order import CloudStorageOrder
from app.models.game_server import GameOrder
from app.models.vps import VpsOrder
from app.services.admin_management import collect_user_orders, get_user_detail, join_admin_notes


def _query_for(model, rows):
    query = MagicMock()
    filtered = MagicMock()
    query.filter.return_value = filtered
    filtered.filter.return_value = filtered
    filtered.order_by.return_value = filtered
    filtered.all.return_value = rows
    filtered.first.return_value = rows[0] if rows else None
    return query


class AdminUserOrdersTests(unittest.TestCase):
    def test_collect_user_orders_merges_newest_first_without_pix(self) -> None:
        now = datetime(2026, 8, 26, 12, 0, 0)
        vps = SimpleNamespace(
            id=11,
            order_type="new",
            hostname="web-01",
            vcpu=2,
            ram_mb=4096,
            disk_gb=40,
            status="active",
            total_cents=9900,
            created_at=now - timedelta(hours=2),
            error_message=None,
            renewal_months=None,
        )
        cloud = SimpleNamespace(
            id=22,
            extra_gb=50,
            renewal_months=None,
            status="paid",
            total_cents=2500,
            created_at=now,
            pix_br_code="secret-pix",
        )
        game = SimpleNamespace(
            id=33,
            game_type="minecraft",
            server_name="survival",
            slots=10,
            ram_mb=2048,
            status="pending_payment",
            total_cents=1990,
            created_at=now - timedelta(hours=1),
            error_message="guest timeout",
            pix_qr_base64="secret-qr",
        )

        db = MagicMock()

        def query(model):
            if model is VpsOrder:
                return _query_for(model, [vps])
            if model is CloudStorageOrder:
                return _query_for(model, [cloud])
            if model is GameOrder:
                return _query_for(model, [game])
            return _query_for(model, [])

        db.query.side_effect = query

        items = collect_user_orders(db, 7)
        self.assertEqual([row["kind"] for row in items], ["cloud", "game", "vps"])
        self.assertEqual(items[0]["title"], "Espaço CyberCloud")
        self.assertEqual(items[1]["title"], "Servidor Minecraft")
        self.assertEqual(items[2]["title"], "Nova VPS")
        self.assertEqual(items[1]["error_message"], "guest timeout")
        serialized = " ".join(str(row) for row in items)
        self.assertNotIn("secret-pix", serialized)
        self.assertNotIn("secret-qr", serialized)
        self.assertNotIn("pix_br_code", serialized)
        self.assertTrue(items[0]["can_delete"])
        self.assertTrue(items[1]["can_delete"])
        self.assertTrue(items[2]["can_delete"])

    def test_collect_user_orders_labels_renewal_and_upgrade(self) -> None:
        db = MagicMock()
        renewal = SimpleNamespace(
            id=1,
            order_type="renewal",
            hostname="box",
            vcpu=1,
            ram_mb=1024,
            disk_gb=30,
            status="paid",
            total_cents=5000,
            created_at=datetime(2026, 8, 1),
            error_message=None,
            renewal_months=3,
        )
        upgrade = SimpleNamespace(
            id=2,
            order_type="upgrade",
            hostname="box",
            vcpu=4,
            ram_mb=8192,
            disk_gb=80,
            status="active",
            total_cents=1200,
            created_at=datetime(2026, 8, 2),
            error_message=None,
            renewal_months=None,
        )
        cloud_renew = SimpleNamespace(
            id=3,
            extra_gb=0,
            renewal_months=2,
            status="paid",
            total_cents=800,
            created_at=datetime(2026, 8, 3),
        )

        def query(model):
            if model is VpsOrder:
                return _query_for(model, [renewal, upgrade])
            if model is CloudStorageOrder:
                return _query_for(model, [cloud_renew])
            return _query_for(model, [])

        db.query.side_effect = query
        items = collect_user_orders(db, 4)
        titles = {row["title"] for row in items}
        self.assertIn("Renovação de VPS", titles)
        self.assertIn("Upgrade de VPS", titles)
        self.assertIn("Renovação CyberCloud", titles)
        self.assertTrue(any("3 mês" in row["description"] for row in items))

    def test_collect_user_orders_admin_notes(self) -> None:
        db = MagicMock()
        vps = SimpleNamespace(
            id=8,
            order_type="admin",
            hostname="web-01",
            vcpu=4,
            ram_mb=8192,
            disk_gb=80,
            status="active",
            total_cents=0,
            created_at=datetime(2026, 8, 26),
            error_message=None,
            renewal_months=None,
            notes="vCPU 2 → 4 · disco 40 GB → 80 GB · cortesia (sem cobrança)",
        )
        cloud = SimpleNamespace(
            id=9,
            extra_gb=50,
            renewal_months=None,
            status="paid",
            total_cents=0,
            created_at=datetime(2026, 8, 26, 1),
            notes="+50 GB de CyberCloud · cortesia (sem cobrança)",
        )

        def query(model):
            if model is VpsOrder:
                return _query_for(model, [vps])
            if model is CloudStorageOrder:
                return _query_for(model, [cloud])
            return _query_for(model, [])

        db.query.side_effect = query
        items = collect_user_orders(db, 2)
        titles = {row["title"] for row in items}
        self.assertIn("Ajuste da equipe", titles)
        self.assertTrue(any("vCPU 2 → 4" in row["description"] for row in items))
        self.assertTrue(any("+50 GB de CyberCloud" in row["description"] for row in items))

    def test_join_admin_notes_skips_empty(self) -> None:
        self.assertEqual(
            join_admin_notes("vCPU 2 → 4", None, "cortesia (sem cobrança)"),
            "vCPU 2 → 4 · cortesia (sem cobrança)",
        )
        self.assertIsNone(join_admin_notes("", None))

    @patch("app.services.admin_management.collect_user_orders")
    @patch("app.services.admin_management.quota_info")
    def test_get_user_detail_includes_orders(self, quota_info, collect_orders) -> None:
        user = SimpleNamespace(
            id=9,
            phone="11999999999",
            email="cliente@example.com",
            name="Cliente",
            is_active=True,
            is_admin=False,
            mfa_enabled=False,
            created_at=datetime(2026, 1, 1),
            cloud_paid_until=None,
            cloud_billing_day=1,
            cloud_monthly_cents=0,
            cloud_suspended_for_billing=False,
            admin_pending_cloud_charge_cents=0,
        )
        db = MagicMock()
        db.get.return_value = user
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        quota_info.return_value = {
            "used_bytes": 1,
            "quota_bytes": 10,
            "base_bytes": 5,
            "vps_bonus_bytes": 0,
            "subscribed_bytes": 0,
            "bonus_bytes": 0,
            "extra_bytes": 5,
            "contracted_gb": 0,
            "billing": None,
        }
        collect_orders.return_value = [
            {
                "kind": "vps",
                "id": 1,
                "title": "Nova VPS",
                "description": "web-01",
                "status": "active",
                "total_cents": 100,
                "created_at": datetime(2026, 8, 26),
                "error_message": None,
            }
        ]

        detail = get_user_detail(db, 9)
        self.assertEqual(detail["orders"][0]["title"], "Nova VPS")
        collect_orders.assert_called_once_with(db, 9)


if __name__ == "__main__":
    unittest.main()
