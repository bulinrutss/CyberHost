import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.analytics import (
    collect_analytics,
    parse_ua,
    sanitize_path,
    sanitize_referrer,
)


class AnalyticsSanitizeTests(unittest.TestCase):
    def test_path_keeps_tab_and_drops_secrets(self) -> None:
        self.assertEqual(sanitize_path("/admin?tab=stats"), "/admin?tab=stats")
        self.assertEqual(
            sanitize_path("/login?ticket=abc123secret&tab=x"),
            "/login?tab=x",
        )
        self.assertEqual(sanitize_path("/order?pix=00020126&code=999999"), "/order")
        self.assertEqual(sanitize_path("https://ruts.dev/cyberhost/dashboard"), "/cyberhost/dashboard")

    def test_referrer_external_is_host_only(self) -> None:
        request = SimpleNamespace(headers={"host": "ruts.dev"})
        self.assertEqual(
            sanitize_referrer("https://google.com/search?q=secret", request),
            "google.com",
        )
        self.assertEqual(
            sanitize_referrer("https://ruts.dev/cyberhost/login", request),
            "/cyberhost/login",
        )

    def test_parse_ua(self) -> None:
        browser, os_name = parse_ua(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        self.assertEqual(browser, "Chrome")
        self.assertEqual(os_name, "Windows")


class AnalyticsCollectTests(unittest.TestCase):
    def test_collect_counts_views_clicks_and_hides_secrets(self) -> None:
        now = datetime.utcnow()
        view = SimpleNamespace(
            name="page_view",
            path="/order",
            label="",
            target="",
            visitor_id="visitor-aaaaaaa",
            session_id="session-bbbbbbb",
            user_id=2,
            is_admin=False,
            referrer="(direto)",
            language="pt-BR",
            ua_browser="Chrome",
            ua_os="Windows",
            viewport_w=1440,
            duration_ms=0,
            scroll_pct=0,
            created_at=now,
        )
        click = SimpleNamespace(
            name="click",
            path="/order",
            label="Contratar VPS",
            target="button",
            visitor_id="visitor-aaaaaaa",
            session_id="session-bbbbbbb",
            user_id=2,
            is_admin=False,
            referrer="",
            language="pt-BR",
            ua_browser="Chrome",
            ua_os="Windows",
            viewport_w=1440,
            duration_ms=0,
            scroll_pct=0,
            created_at=now - timedelta(minutes=1),
        )
        db = MagicMock()
        query = MagicMock()
        query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            view,
            click,
        ]
        user_query = MagicMock()
        user_query.filter.return_value.all.return_value = [
            SimpleNamespace(id=2, name="Ana")
        ]

        def side_effect(model):
            from app.models.user import User

            if model is User:
                return user_query
            return query

        db.query.side_effect = side_effect
        stats = collect_analytics(db, 7)

        self.assertEqual(stats["totals"]["page_views"], 1)
        self.assertEqual(stats["totals"]["clicks"], 1)
        self.assertEqual(stats["totals"]["identified_users"], 1)
        self.assertEqual(stats["top_clicks"][0]["key"], "Contratar VPS")
        self.assertEqual(stats["recent"][0]["user_name"], "Ana")
        blob = str(stats)
        self.assertNotIn("pix", blob)
        self.assertNotIn("ticket", blob)


class AnalyticsIngestGuardTests(unittest.TestCase):
    def test_unknown_event_name_is_ignored(self) -> None:
        from app.services.analytics import ingest_events

        db = MagicMock()
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "Chrome", "host": "ruts.dev", "cf-connecting-ip": ""},
        )
        with patch("app.services.analytics.auth_throttle") as throttle:
            throttle.client_ip.return_value = "203.0.113.9"
            throttle.check_lock.return_value = 0
            throttle.add_hit.return_value = 0
            stored = ingest_events(
                db,
                request,
                [{"name": "password", "path": "/login", "label": "segredo"}],
                None,
            )
        self.assertEqual(stored, 0)
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
