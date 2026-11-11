import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_db
from app.models.auth_security import AuthMfaTicket, AuthPhoneChallenge, AuthThrottle
from app.models.user import User
from app.services import whatsapp
from app.utils.phone import to_whatsapp_e164
from pydantic import ValidationError

from app.config import Settings


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
        "whatsapp_enabled": True,
        "whatsapp_access_token": "token",
        "whatsapp_phone_number_id": "123",
        "whatsapp_template_name": "verification_code",
        "whatsapp_template_language": "pt_BR",
        "whatsapp_template_button": True,
        "whatsapp_graph_version": "v22.0",
        "whatsapp_otp_ttl_seconds": 600,
        "whatsapp_resend_seconds": 60,
        "whatsapp_send_ip_max": 20,
        "whatsapp_send_ip_window_seconds": 3600,
        "whatsapp_send_phone_max": 20,
        "whatsapp_send_phone_window_seconds": 3600,
        "whatsapp_verify_phone_max": 8,
        "whatsapp_verify_phone_window_seconds": 900,
        "auth_login_ip_max": 20,
        "auth_login_ip_window_seconds": 600,
        "auth_login_phone_fail_max": 8,
        "auth_login_phone_window_seconds": 900,
        "auth_register_ip_max": 20,
        "auth_register_ip_window_seconds": 3600,
        "auth_mfa_ip_max": 10,
        "auth_mfa_ticket_seconds": 120,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PhoneE164Tests(unittest.TestCase):
    def test_adds_brazil_country_code(self) -> None:
        self.assertEqual(to_whatsapp_e164("11988887777"), "5511988887777")
        self.assertEqual(to_whatsapp_e164("+55 (11) 98888-7777"), "5511988887777")


class WhatsAppConfigTests(unittest.TestCase):
    def test_enabled_requires_credentials(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_environment="development",
                abacatepay_enabled=False,
                secret_key="k" * 40,
                whatsapp_enabled=True,
                whatsapp_access_token="",
                whatsapp_phone_number_id="",
            )


class WhatsAppOtpApiTests(unittest.TestCase):
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
                AuthPhoneChallenge.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.password = "correct-horse"
        self.user = User(
            phone="11988880001",
            email="cliente@example.com",
            name="Cliente",
            hashed_password=hash_password(self.password),
            is_active=True,
            is_admin=False,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        app = FastAPI()
        app.include_router(auth_router, prefix="/api/auth")

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.settings = _settings()
        self.patches = [
            patch("app.services.whatsapp.get_settings", return_value=self.settings),
            patch("app.services.phone_otp.get_settings", return_value=self.settings),
            patch("app.services.auth_throttle.get_settings", return_value=self.settings),
            patch("app.auth.get_settings", return_value=self.settings),
            patch("app.services.whatsapp.send_authentication_code"),
            patch("app.services.phone_otp.generate_otp", return_value="123456"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.db.close()
        self.engine.dispose()

    def test_status_reports_required(self) -> None:
        res = self.client.get("/api/auth/phone-verification")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["required"])
        self.assertEqual(res.json()["channel"], "whatsapp")

    def test_register_requires_otp_when_enabled(self) -> None:
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
            "/api/auth/whatsapp/send",
            json={"phone": "11977771111"},
        )
        self.assertEqual(sent.status_code, 200, sent.text)
        ticket = sent.json()["ticket"]
        self.assertTrue(ticket)
        self.assertNotIn("123456", sent.text)

        created = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771111",
                "email": "novo@example.com",
                "name": "Novo",
                "password": "password1",
                "whatsapp_ticket": ticket,
                "whatsapp_code": "123456",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["phone"], "11977771111")

    def test_wrong_code_is_rejected(self) -> None:
        sent = self.client.post(
            "/api/auth/whatsapp/send",
            json={"phone": "11977771112"},
        )
        ticket = sent.json()["ticket"]
        bad = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771112",
                "email": "outro@example.com",
                "name": "Outro",
                "password": "password1",
                "whatsapp_ticket": ticket,
                "whatsapp_code": "000000",
            },
        )
        self.assertEqual(bad.status_code, 400)

    def test_send_rejects_existing_phone(self) -> None:
        res = self.client.post(
            "/api/auth/whatsapp/send",
            json={"phone": self.user.phone},
        )
        self.assertEqual(res.status_code, 400)

    def test_undeliverable_number_maps_to_client_error(self) -> None:
        self.patches[4].stop()
        with patch(
            "app.services.whatsapp.send_authentication_code",
            side_effect=HTTPException(
                status_code=400,
                detail="Este número não tem WhatsApp ou não pode receber a mensagem.",
            ),
        ):
            res = self.client.post(
                "/api/auth/whatsapp/send",
                json={"phone": "11977771113"},
            )
        self.assertEqual(res.status_code, 400)
        self.assertIn("WhatsApp", res.json()["detail"])


class WhatsAppGraphErrorTests(unittest.TestCase):
    def test_graph_error_does_not_leak_token(self) -> None:
        class FakeResponse:
            status_code = 401

            def json(self):
                return {"error": {"message": "Invalid OAuth access token", "code": 190}}

        with patch(
            "app.services.whatsapp.get_settings",
            return_value=_settings(),
        ), patch("app.services.whatsapp.httpx.post", return_value=FakeResponse()):
            with self.assertRaises(HTTPException) as raised:
                whatsapp.send_authentication_code("11988887777", "123456")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("token", raised.exception.detail.lower())


class WhatsAppDisabledRegisterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, AuthThrottle.__table__, AuthPhoneChallenge.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        app = FastAPI()
        app.include_router(auth_router, prefix="/api/auth")

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.settings = _settings(whatsapp_enabled=False)
        self.patches = [
            patch("app.services.whatsapp.get_settings", return_value=self.settings),
            patch("app.services.phone_otp.get_settings", return_value=self.settings),
            patch("app.services.auth_throttle.get_settings", return_value=self.settings),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.db.close()
        self.engine.dispose()

    def test_register_without_otp_when_disabled(self) -> None:
        res = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977772222",
                "email": "livre@example.com",
                "name": "Livre",
                "password": "password1",
            },
        )
        self.assertEqual(res.status_code, 201, res.text)


if __name__ == "__main__":
    unittest.main()
