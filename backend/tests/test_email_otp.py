import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.config import Settings
from app.database import Base, get_db
from app.models.auth_security import AuthEmailChallenge, AuthMfaTicket, AuthThrottle
from app.models.user import User
from app.services import mailer


def _load_auth_router():
    if "app.api.auth" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.auth import router

    return router


auth_router = _load_auth_router()


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "secret_key": "k" * 40,
        "app_environment": "development",
        "whatsapp_enabled": False,
        "email_otp_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "resend",
        "smtp_password": "secret",
        "smtp_from": "cyberhost@ruts.dev",
        "smtp_from_name": "CyberHost",
        "smtp_starttls": True,
        "smtp_ssl": False,
        "email_otp_ttl_seconds": 600,
        "email_otp_resend_seconds": 60,
        "email_send_ip_max": 20,
        "email_send_ip_window_seconds": 3600,
        "email_send_max": 20,
        "email_send_window_seconds": 3600,
        "email_verify_max": 8,
        "email_verify_window_seconds": 900,
        "auth_login_ip_max": 20,
        "auth_login_ip_window_seconds": 600,
        "auth_login_phone_fail_max": 8,
        "auth_login_phone_window_seconds": 900,
        "auth_register_ip_max": 20,
        "auth_register_ip_window_seconds": 3600,
        "auth_mfa_ip_max": 10,
        "whatsapp_send_ip_max": 10,
        "whatsapp_send_ip_window_seconds": 3600,
        "whatsapp_send_phone_max": 5,
        "whatsapp_send_phone_window_seconds": 3600,
        "whatsapp_verify_phone_max": 8,
        "whatsapp_verify_phone_window_seconds": 900,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class EmailOtpConfigTests(unittest.TestCase):
    def test_enabled_requires_smtp(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_environment="development",
                abacatepay_enabled=False,
                secret_key="k" * 40,
                email_otp_enabled=True,
                smtp_host="",
                smtp_from="",
            )


class EmailOtpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                AuthThrottle.__table__,
                AuthMfaTicket.__table__,
                AuthEmailChallenge.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11988880001",
            email="cliente@example.com",
            name="Cliente",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.db.add(self.user)
        self.db.commit()

        app = FastAPI()
        app.include_router(auth_router, prefix="/api/auth")

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.settings = _settings()
        self.patches = [
            patch("app.services.mailer.get_settings", return_value=self.settings),
            patch("app.services.email_otp.get_settings", return_value=self.settings),
            patch("app.services.whatsapp.get_settings", return_value=self.settings),
            patch("app.services.auth_throttle.get_settings", return_value=self.settings),
            patch("app.services.mailer.send_otp_email"),
            patch("app.services.email_otp.generate_otp", return_value="123456"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.db.close()
        self.engine.dispose()

    def test_status_reports_required(self) -> None:
        res = self.client.get("/api/auth/email-verification")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["required"])
        self.assertEqual(res.json()["channel"], "email")

    def test_register_requires_code_when_enabled(self) -> None:
        res = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771111",
                "email": "novo@example.com",
                "name": "Novo",
                "password": "password1",
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_send_and_register_with_valid_code(self) -> None:
        sent = self.client.post(
            "/api/auth/email/send",
            json={"email": "novo@example.com"},
        )
        self.assertEqual(sent.status_code, 200, sent.text)
        ticket = sent.json()["ticket"]
        self.assertNotIn("123456", sent.text)

        created = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771111",
                "email": "novo@example.com",
                "name": "Novo",
                "password": "password1",
                "email_ticket": ticket,
                "email_code": "123456",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["email"], "novo@example.com")

    def test_wrong_code_is_rejected(self) -> None:
        sent = self.client.post("/api/auth/email/send", json={"email": "outro@example.com"})
        ticket = sent.json()["ticket"]
        bad = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771112",
                "email": "outro@example.com",
                "name": "Outro",
                "password": "password1",
                "email_ticket": ticket,
                "email_code": "000000",
            },
        )
        self.assertEqual(bad.status_code, 400)

    def test_send_rejects_existing_email(self) -> None:
        res = self.client.post(
            "/api/auth/email/send",
            json={"email": self.user.email},
        )
        self.assertEqual(res.status_code, 400)


class EmailSmtpErrorTests(unittest.TestCase):
    def test_smtp_error_does_not_leak_secret(self) -> None:
        with patch(
            "app.services.mailer.get_settings",
            return_value=_settings(),
        ), patch(
            "app.services.mailer.smtplib.SMTP",
            side_effect=OSError("auth failed password=secret"),
        ):
            with self.assertRaises(HTTPException) as raised:
                mailer.send_otp_email("novo@example.com", "123456", 600)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("secret", raised.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
