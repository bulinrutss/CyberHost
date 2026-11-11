import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.admin_stats import (
    build_daily_series,
    classify_order_status,
    collect_admin_stats,
    date_keys,
)


class AdminStatsHelperTests(unittest.TestCase):
    def test_classify_order_status(self) -> None:
        self.assertEqual(classify_order_status("active"), "completed")
        self.assertEqual(classify_order_status("paid"), "completed")
        self.assertEqual(classify_order_status("pending_payment"), "pending")
        self.assertEqual(classify_order_status("provisioning"), "pending")
        self.assertEqual(classify_order_status("cancelled"), "denied")
        self.assertEqual(classify_order_status("failed"), "error")
        self.assertEqual(classify_order_status(SimpleNamespace(value="cancelled")), "denied")

    def test_daily_series_fills_window_and_skips_pix(self) -> None:
        now = datetime(2026, 8, 26, 18, 0, 0)
        rows = [
            (datetime(2026, 8, 26, 10, 0, 0), "active", 9900),
            (datetime(2026, 8, 26, 11, 0, 0), "failed", 1000),
            (datetime(2026, 8, 25, 9, 0, 0), "cancelled", 500),
            (datetime(2026, 8, 20, 9, 0, 0), "paid", 100),
        ]
        series = build_daily_series(7, rows, now)
        self.assertEqual(len(series), 7)
        self.assertEqual([day["date"] for day in series][0], "2026-08-20")
        self.assertEqual(series[-1]["date"], "2026-08-26")
        today = series[-1]
        self.assertEqual(today["completed"], 1)
        self.assertEqual(today["error"], 1)
        self.assertEqual(today["revenue_cents"], 9900)
        yesterday = series[-2]
        self.assertEqual(yesterday["denied"], 1)
        first = series[0]
        self.assertEqual(first["completed"], 1)
        dumped = str(series)
        self.assertNotIn("pix", dumped)

    def test_date_keys_length(self) -> None:
        keys = date_keys(30, datetime(2026, 8, 26))
        self.assertEqual(len(keys), 30)
        self.assertEqual(keys[-1], "2026-08-26")


class AdminStatsCollectTests(unittest.TestCase):
    def test_collect_counts_orders_clients_and_events(self) -> None:
        now = datetime(2026, 8, 26, 12, 0, 0)
        customer = SimpleNamespace(
            id=2,
            name="Ana",
            phone="11999999999",
            is_admin=False,
            is_active=True,
            cloud_contracted_gb=50,
            cloud_suspended_for_billing=False,
            cloud_paid_until=None,
            created_at=now,
        )
        admin = SimpleNamespace(
            id=1,
            name="Admin",
            phone="11000000000",
            is_admin=True,
            is_active=True,
            cloud_contracted_gb=0,
            cloud_suspended_for_billing=False,
            cloud_paid_until=None,
            created_at=now,
        )
        vm = SimpleNamespace(
            id=9,
            user_id=2,
            vm_name="ana-web",
            status="running",
            vcpu=4,
            ram_mb=8192,
            disk_gb=60,
            ip_address="192.168.0.10",
            paid_until=now,
            suspended_for_billing=False,
            error_message=None,
            updated_at=now,
            created_at=now,
            order_id=1,
        )
        error_vm = SimpleNamespace(
            id=10,
            user_id=2,
            vm_name="ana-db",
            status="error",
            vcpu=2,
            ram_mb=4096,
            disk_gb=40,
            ip_address=None,
            paid_until=None,
            suspended_for_billing=True,
            error_message="clone timeout",
            updated_at=now,
            created_at=now,
            order_id=None,
        )
        paid = SimpleNamespace(
            id=1,
            user_id=2,
            status="active",
            order_type="new",
            hostname="ana-web",
            total_cents=12490,
            created_at=now,
            error_message=None,
            provision_step=None,
            pix_br_code="SECRET",
        )
        failed = SimpleNamespace(
            id=2,
            user_id=2,
            status="failed",
            order_type="upgrade",
            hostname="ana-db",
            total_cents=2000,
            created_at=now - timedelta(hours=2),
            error_message="guest auth",
            provision_step="guest",
        )
        cancelled = SimpleNamespace(
            id=3,
            user_id=2,
            status="cancelled",
            extra_gb=50,
            renewal_months=None,
            total_cents=2500,
            created_at=now - timedelta(hours=1),
        )

        db = MagicMock()
        db.query.side_effect = self._queries(
            users=[admin, customer],
            instances=[vm, error_vm],
            vps_orders=[paid, failed],
            cloud_orders=[cancelled],
            game_orders=[],
            game_servers=[],
            cloud_used=1024,
            cloud_files=3,
        )

        stats = collect_admin_stats(db, 7)

        self.assertEqual(stats["clients"]["total"], 1)
        self.assertEqual(stats["clients"]["admins"], 1)
        self.assertEqual(stats["orders"]["completed"], 1)
        self.assertEqual(stats["orders"]["error"], 1)
        self.assertEqual(stats["orders"]["denied"], 1)
        self.assertEqual(stats["orders"]["revenue_cents"], 12490)
        self.assertEqual(stats["host"]["vps_running"], 1)
        self.assertEqual(stats["host"]["vps_error"], 1)
        self.assertEqual(stats["host"]["allocated_vcpu"], 6)
        self.assertEqual(stats["top_clients"][0]["name"], "Ana")
        self.assertEqual(stats["top_clients"][0]["spent_cents"], 12490)
        self.assertTrue(any(ev["level"] == "error" for ev in stats["events"]))
        failed_event = next(ev for ev in stats["events"] if ev.get("order_id") == 2)
        self.assertTrue(failed_event["can_delete"])
        paid_event = next(ev for ev in stats["events"] if ev.get("order_id") == 1)
        self.assertTrue(paid_event["can_delete"])
        machine_event = next(ev for ev in stats["events"] if ev.get("instance_id") == 10)
        self.assertFalse(machine_event["can_delete"])
        blob = str(stats)
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("pix_br_code", blob)
        self.assertEqual(len(stats["daily"]), 7)

    def _queries(self, **payload):
        users_q = MagicMock()
        users_q.all.return_value = payload["users"]

        inst_q = MagicMock()
        inst_q.filter.return_value.order_by.return_value.all.return_value = payload["instances"]

        vps_q = MagicMock()
        vps_q.filter.return_value.all.return_value = payload["vps_orders"]

        cloud_q = MagicMock()
        cloud_q.filter.return_value.all.return_value = payload["cloud_orders"]

        game_q = MagicMock()
        game_q.filter.return_value.all.return_value = payload["game_orders"]

        gsrv_q = MagicMock()
        gsrv_q.filter.return_value.all.return_value = payload["game_servers"]

        used_q = MagicMock()
        used_q.filter.return_value.scalar.return_value = payload["cloud_used"]

        files_q = MagicMock()
        files_q.filter.return_value.scalar.return_value = payload["cloud_files"]

        calls = iter(
            [users_q, inst_q, vps_q, cloud_q, game_q, gsrv_q, used_q, files_q]
        )

        def query(_model):
            try:
                return next(calls)
            except StopIteration:
                leftover = MagicMock()
                leftover.filter.return_value.all.return_value = []
                leftover.filter.return_value.scalar.return_value = 0
                leftover.all.return_value = []
                return leftover

        return query


if __name__ == "__main__":
    unittest.main()
