import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.nginx_proxy_admin import list_proxy_entries


class NginxProxyListTests(unittest.TestCase):
    def test_list_includes_manual_site_and_vps(self) -> None:
        now = datetime(2026, 9, 2, 12, 0, 0)
        manual = SimpleNamespace(
            id=1,
            domain="app.example.com",
            mode="redirect",
            redirect_url="https://destino.com/",
            upstream_url=None,
            include_www=False,
            notes="teste",
            created_at=now,
        )
        site = SimpleNamespace(
            id=5,
            site_slug="loja",
            domain="loja.com",
            port=30123,
            status=SimpleNamespace(value="running"),
            created_at=now,
        )
        conn = SimpleNamespace(
            id=9,
            domain="game.example.com",
            public_port=40001,
            created_at=now,
        )
        instance = SimpleNamespace(id=2, vm_name="vm-game", status=SimpleNamespace(value="running"))

        db = MagicMock()

        def query_side_effect(*models):
            q = MagicMock()
            if len(models) == 1 and models[0].__name__ == "NginxProxyRoute":
                q.order_by.return_value.all.return_value = [manual]
            elif len(models) == 1 and models[0].__name__ == "WebSite":
                q.filter.return_value.order_by.return_value.all.return_value = [site]
            elif len(models) == 2:
                joined = MagicMock()
                joined.filter.return_value.order_by.return_value.all.return_value = [(conn, instance)]
                q.join.return_value = joined
            return q

        db.query.side_effect = query_side_effect
        settings = SimpleNamespace(vps_public_ip="203.0.113.10")

        with (
            patch("app.services.nginx_proxy_admin.manual_cert_paths", return_value=None),
            patch("app.services.nginx_proxy_admin.platform_subdomain_for_site", return_value="loja.ruts.dev"),
            patch("app.services.web_ssl.has_certificate", return_value=True),
            patch("app.services.vps_connection_ssl.has_certificate", return_value=False),
            patch("app.services.nginx_proxy_admin.resolved_vps_public_ip", return_value="203.0.113.10"),
        ):
            items = list_proxy_entries(db, settings)

        keys = {item["key"] for item in items}
        self.assertIn("manual-1", keys)
        self.assertIn("site-5-custom", keys)
        self.assertIn("site-5-platform", keys)
        self.assertIn("vps-9", keys)

        manual_item = next(item for item in items if item["key"] == "manual-1")
        self.assertEqual(manual_item["mode"], "redirect")
        self.assertEqual(manual_item["target"], "https://destino.com/")
        self.assertTrue(manual_item["deletable"])


if __name__ == "__main__":
    unittest.main()
