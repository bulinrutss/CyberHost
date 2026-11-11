import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.user import User
from app.models.vps import VpsInstance, VpsStatus
from app.services import email_templates, mailer
from app.services.billing_reminders import (
    collect_due_items,
    reminder_offset,
    send_due_reminders,
)


def _settings(**overrides):
    values = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "resend",
        "smtp_password": "secret",
        "smtp_from": "cyberhost@ruts.dev",
        "smtp_from_name": "CyberHost",
        "smtp_starttls": True,
        "smtp_ssl": False,
        "resolved_frontend_url": "https://ruts.dev",
        "billing_reminder_enabled": True,
        "email_otp_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Query:
    def __init__(self, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first


class ReminderOffsetTests(unittest.TestCase):
    def test_schedule_matches_requested_days(self) -> None:
        self.assertEqual(reminder_offset(10), 10)
        self.assertEqual(reminder_offset(5), 5)
        self.assertEqual(reminder_offset(3), 3)
        self.assertEqual(reminder_offset(2), 2)
        self.assertEqual(reminder_offset(1), 1)
        self.assertEqual(reminder_offset(-1), -1)
        self.assertEqual(reminder_offset(-5), -5)
        self.assertIsNone(reminder_offset(4))
        self.assertIsNone(reminder_offset(0))
        self.assertIsNone(reminder_offset(-6))
        self.assertIsNone(reminder_offset(9))


class EmailTemplateTests(unittest.TestCase):
    def test_otp_html_has_logo_and_no_raw_angle_in_code(self) -> None:
        subject, text, html = email_templates.otp_content(
            code="12<a>6",
            minutes=10,
            logo_src="cid:cyberhost-logo",
        )
        self.assertEqual(subject, "Seu código de verificação CyberHost")
        self.assertIn("12<a>6", text)
        self.assertIn("12&lt;a&gt;6", html)
        self.assertIn("cid:cyberhost-logo", html)
        self.assertIn("#06c96c", html)
        self.assertNotIn("secret", html)

    def test_billing_html_lists_vps_and_cta(self) -> None:
        subject, text, html = email_templates.billing_content(
            name="Maria Silva",
            items=[
                {
                    "title": "web-01",
                    "detail": "2 vCPU",
                    "due_label": "Vence em 05/09/2026",
                    "price_label": "R$ 99,00",
                    "badge": "Vence em 10 dias",
                    "overdue": False,
                }
            ],
            cta_url="https://ruts.dev/cyberhost/dashboard/vps/3",
            logo_src="https://ruts.dev/cyberhost/logo2.png",
            most_urgent_days=10,
        )
        self.assertIn("vence em 10 dias", subject.lower())
        self.assertIn("web-01", html)
        self.assertIn("Ver no painel", html)
        self.assertIn("https://ruts.dev/cyberhost/dashboard/vps/3", html)
        self.assertIn("logo2.png", html)
        self.assertIn("Oi, Maria", html)

    def test_overdue_subject(self) -> None:
        subject, _, html = email_templates.billing_content(
            name="João",
            items=[{"title": "CyberCloud", "detail": "50 GB", "due_label": "Venceu", "price_label": "", "overdue": True, "badge": "Vencido há 2 dia(s)"}],
            cta_url="https://ruts.dev/cyberhost/dashboard/files",
            logo_src="cid:cyberhost-logo",
            most_urgent_days=-2,
        )
        self.assertIn("vencido", subject.lower())
        self.assertIn("#e53e3e", html)


class PanelUrlTests(unittest.TestCase):
    def test_production_prefixes_cyberhost(self) -> None:
        with patch("app.services.mailer.get_settings", return_value=_settings()):
            self.assertEqual(
                mailer.panel_url("/dashboard/vps/1"),
                "https://ruts.dev/cyberhost/dashboard/vps/1",
            )

    def test_localhost_keeps_path(self) -> None:
        with patch(
            "app.services.mailer.get_settings",
            return_value=_settings(resolved_frontend_url="http://localhost:3000"),
        ):
            self.assertEqual(mailer.panel_url("dashboard/files"), "http://localhost:3000/dashboard/files")


class CollectRemindersTests(unittest.TestCase):
    def _db(self, *, instances=None, users=None, cloud_users=None):
        db = MagicMock()
        user_map = {u.id: u for u in (users or [])}

        def get(_model, key):
            return user_map.get(key)

        db.get.side_effect = get

        def query(model):
            if model is VpsInstance:
                return _Query(rows=instances or [])
            if model is User:
                return _Query(rows=cloud_users or [])
            return _Query(rows=[], first=None)

        db.query.side_effect = query
        return db

    def test_collects_vps_ten_days_out(self) -> None:
        now = datetime(2026, 8, 26, 15, 0, 0)
        user = SimpleNamespace(id=2, email="ana@example.com", name="Ana")
        inst = SimpleNamespace(
            id=11,
            user_id=2,
            vm_name="web-01",
            status=VpsStatus.RUNNING,
            paid_until=now + timedelta(days=10),
            vcpu=2,
            ram_mb=4096,
            disk_gb=40,
            plan_id=None,
            billing_day=5,
            suspended_for_billing=False,
            custom_monthly_cents=9900,
        )
        items = collect_due_items(self._db(instances=[inst], users=[user]), now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["offset_days"], 10)
        self.assertEqual(items[0]["kind"], "vps")
        self.assertIn("web-01", items[0]["title"])

    def test_skips_four_days_and_missing_email(self) -> None:
        now = datetime(2026, 8, 26, 15, 0, 0)
        with_mail = SimpleNamespace(id=2, email="ana@example.com", name="Ana")
        no_mail = SimpleNamespace(id=3, email=None, name="Sem")
        due_four = SimpleNamespace(
            id=11,
            user_id=2,
            vm_name="web-01",
            status=VpsStatus.RUNNING,
            paid_until=now + timedelta(days=4),
            vcpu=2,
            ram_mb=2048,
            disk_gb=30,
            plan_id=None,
            billing_day=1,
            suspended_for_billing=False,
            custom_monthly_cents=1000,
        )
        due_ten_no_email = SimpleNamespace(
            id=12,
            user_id=3,
            vm_name="box",
            status=VpsStatus.RUNNING,
            paid_until=now + timedelta(days=10),
            vcpu=2,
            ram_mb=2048,
            disk_gb=30,
            plan_id=None,
            billing_day=1,
            suspended_for_billing=False,
            custom_monthly_cents=1000,
        )
        items = collect_due_items(
            self._db(instances=[due_four, due_ten_no_email], users=[with_mail, no_mail]),
            now=now,
        )
        self.assertEqual(items, [])

    def test_collects_cloud_two_days_overdue(self) -> None:
        now = datetime(2026, 8, 26, 15, 0, 0)
        user = SimpleNamespace(
            id=8,
            email="cloud@example.com",
            name="Caio",
            cloud_contracted_gb=50,
            cloud_paid_until=now - timedelta(days=2),
            cloud_monthly_cents=2500,
            cloud_billing_day=24,
            cloud_suspended_for_billing=False,
        )
        items = collect_due_items(self._db(cloud_users=[user]), now=now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "cloud")
        self.assertEqual(items[0]["offset_days"], -2)
        self.assertTrue(items[0]["overdue"])


class SendRemindersTests(unittest.TestCase):
    @patch("app.services.billing_reminders._mark_sent", return_value=True)
    @patch("app.services.billing_reminders.mailer.send_email")
    @patch("app.services.billing_reminders.mailer.smtp_configured", return_value=True)
    @patch("app.services.billing_reminders.mailer.load_logo_bytes", return_value=None)
    @patch("app.services.billing_reminders.get_settings", return_value=_settings())
    @patch("app.services.billing_reminders.collect_due_items")
    def test_one_email_per_user(self, collect, _settings_p, _logo, _smtp, send_email, _mark) -> None:
        collect.return_value = [
            {
                "kind": "vps",
                "resource_id": 1,
                "user_id": 9,
                "email": "ana@example.com",
                "name": "Ana",
                "due_on": datetime(2026, 9, 5).date(),
                "offset_days": 10,
                "overdue": False,
                "title": "web-01",
                "detail": "2 vCPU",
                "due_label": "Vence em 05/09/2026",
                "price_label": "R$ 99,00",
                "badge": "Vence em 10 dias",
                "cta_path": "/dashboard/vps/1",
            },
            {
                "kind": "cloud",
                "resource_id": 9,
                "user_id": 9,
                "email": "ana@example.com",
                "name": "Ana",
                "due_on": datetime(2026, 9, 5).date(),
                "offset_days": 10,
                "overdue": False,
                "title": "CyberCloud",
                "detail": "50 GB",
                "due_label": "Vence em 05/09/2026",
                "price_label": "R$ 25,00",
                "badge": "Vence em 10 dias",
                "cta_path": "/dashboard/files",
            },
        ]
        sent = send_due_reminders(MagicMock())
        self.assertEqual(sent, 1)
        send_email.assert_called_once()
        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "ana@example.com")
        self.assertIn("web-01", kwargs["html"])
        self.assertIn("CyberCloud", kwargs["html"])
        self.assertNotIn("secret", kwargs["html"])
        self.assertNotIn("secret", kwargs["text"])

    @patch("app.services.billing_reminders.mailer.send_email")
    @patch("app.services.billing_reminders.mailer.smtp_configured", return_value=False)
    @patch("app.services.billing_reminders.get_settings", return_value=_settings())
    def test_noop_without_smtp(self, _settings_p, _smtp, send_email) -> None:
        self.assertEqual(send_due_reminders(MagicMock()), 0)
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
