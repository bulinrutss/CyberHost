"""Admin: sites na conta e exclusão."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.web_site import WebSiteStatus
from app.services.admin_management import collect_user_orders, delete_web_site, get_user_detail
from app.services.web_process import destroy_site


class DestroySiteTests(unittest.TestCase):
    def test_destroy_site_purges_data_and_marks_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_dir = root / "2" / "7"
            site_dir.mkdir(parents=True)
            (site_dir / "public").mkdir()
            (site_dir / "public" / "index.html").write_text("ok", encoding="utf-8")
            site = SimpleNamespace(
                id=7,
                site_slug="meu-site",
                domain="example.com",
                data_path=str(site_dir),
                process_pid=None,
                status=WebSiteStatus.RUNNING,
                error_message="x",
            )
            settings = SimpleNamespace(
                web_sites_data_path=str(root),
                web_nginx_reload=False,
            )
            with patch("app.services.web_process.stop_site") as stop_site:
                with patch("app.services.web_nginx.remove_snippet"):
                    msg = destroy_site(site, settings)
            stop_site.assert_called_once()
            self.assertEqual(msg, "Site meu-site apagado")
            self.assertEqual(site.status, WebSiteStatus.DELETED)
            self.assertIsNone(site.domain)
            self.assertFalse(site_dir.exists())


class AdminWebSitesDetailTests(unittest.TestCase):
    @patch("app.services.admin_management.collect_user_orders")
    @patch("app.services.admin_management.quota_info")
    def test_get_user_detail_includes_web_sites(self, quota_info, collect_orders) -> None:
        user = SimpleNamespace(
            id=9,
            phone="5511999999999",
            email="a@b.com",
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
            cloud_contracted_gb=0,
        )
        site = SimpleNamespace(
            id=3,
            site_slug="loja",
            domain=None,
            ram_mb=512,
            disk_mb=2048,
            php_enabled=False,
            port=30001,
            status=WebSiteStatus.RUNNING,
            paid_until=None,
            suspended_for_billing=False,
            created_at=datetime(2026, 2, 1),
        )
        db = MagicMock()
        db.get.return_value = user

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "VpsInstance":
                q.filter.return_value.order_by.return_value.all.return_value = []
            elif model.__name__ == "WebSite":
                q.filter.return_value.order_by.return_value.all.return_value = [site]
            return q

        db.query.side_effect = query_side_effect
        quota_info.return_value = {
            "used_bytes": 0,
            "quota_bytes": 1,
            "base_bytes": 1,
            "vps_bonus_bytes": 0,
            "subscribed_bytes": 0,
            "bonus_bytes": 0,
            "extra_bytes": 0,
            "contracted_gb": 0,
            "billing": None,
        }
        collect_orders.return_value = []

        detail = get_user_detail(db, 9)
        self.assertEqual(len(detail["web_sites"]), 1)
        self.assertEqual(detail["web_sites"][0]["site_slug"], "loja")


class CollectWebOrdersTests(unittest.TestCase):
    def test_collect_user_orders_includes_web(self) -> None:
        order = SimpleNamespace(
            id=12,
            user_id=2,
            site_slug="blog",
            domain=None,
            ram_mb=256,
            disk_mb=512,
            php_enabled=True,
            total_cents=299,
            status=SimpleNamespace(value="active"),
            created_at=datetime(2026, 3, 1),
            error_message=None,
        )
        db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            name = getattr(model, "__name__", str(model))
            if name == "VpsInstance":
                q.filter.return_value.all.return_value = []
            elif name == "GameServer":
                q.filter.return_value.all.return_value = []
            elif name == "WebSite":
                q.filter.return_value.all.return_value = []
            elif name == "VpsOrder":
                q.filter.return_value.order_by.return_value.all.return_value = []
            elif name == "CloudStorageOrder":
                q.filter.return_value.order_by.return_value.all.return_value = []
            elif name == "GameOrder":
                q.filter.return_value.order_by.return_value.all.return_value = []
            elif name == "WebOrder":
                q.filter.return_value.order_by.return_value.all.return_value = [order]
            return q

        db.query.side_effect = query_side_effect
        items = collect_user_orders(db, 2)
        self.assertEqual(items[0]["kind"], "web")
        self.assertIn("PHP", items[0]["description"])


class DeleteWebSiteAdminTests(unittest.TestCase):
    @patch("app.services.web_process.destroy_site")
    def test_delete_web_site_commits(self, destroy_site_mock) -> None:
        site = SimpleNamespace(
            id=5,
            user_id=2,
            site_slug="x",
            status=WebSiteStatus.RUNNING,
        )
        admin = SimpleNamespace(id=1)
        db = MagicMock()
        db.get.return_value = site
        destroy_site_mock.return_value = "Site x apagado"

        result = delete_web_site(db, admin, 5)
        destroy_site_mock.assert_called_once_with(site)
        db.commit.assert_called_once()
        self.assertEqual(result["site_id"], 5)



if __name__ == "__main__":
    unittest.main()
