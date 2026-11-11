import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import hash_password
from app.database import Base, get_db
from app.models.auth_security import AuthMfaTicket, AuthSession, AuthThrottle
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.services import auth_throttle
from app.services.totp import generate_secret, totp_code, verify_totp


def _load_auth_router():
    """Evita `app.api.__init__` (pyVmomi) no Windows."""
    if "app.api.auth" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.auth import router

    return router


auth_router = _load_auth_router()


def _throttle_settings(**overrides) -> SimpleNamespace:
    values = {
        "secret_key": "k" * 40,
        "auth_login_ip_max": 20,
        "auth_login_ip_window_seconds": 600,
        "auth_login_phone_fail_max": 8,
        "auth_login_phone_window_seconds": 900,
        "auth_register_ip_max": 5,
        "auth_register_ip_window_seconds": 3600,
        "auth_mfa_ip_max": 10,
        "auth_mfa_ticket_seconds": 120,
        "admin_mfa_required": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TotpTests(unittest.TestCase):
    def test_code_roundtrip(self) -> None:
        secret = generate_secret()
        code = totp_code(secret)
        self.assertTrue(verify_totp(secret, code))
        self.assertFalse(verify_totp(secret, "000000"))


class ClientIpTests(unittest.TestCase):
    def _request(self, peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": headers,
                "client": (peer, 1234),
                "server": ("127.0.0.1", 80),
            }
        )

    def test_trusts_cf_from_proxy(self) -> None:
        request = self._request("127.0.0.1", [(b"cf-connecting-ip", b"203.0.113.10")])
        self.assertEqual(auth_throttle.client_ip(request), "203.0.113.10")

    def test_ignores_spoofed_cf_from_public_peer(self) -> None:
        request = self._request("203.0.113.9", [(b"cf-connecting-ip", b"1.2.3.4")])
        self.assertEqual(auth_throttle.client_ip(request), "203.0.113.9")


class AuthSecurityApiTests(unittest.TestCase):
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
                AuthSession.__table__,
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
        self.admin = User(
            phone="11988880002",
            name="Admin",
            hashed_password=hash_password(self.password),
            is_active=True,
            is_admin=True,
        )
        self.db.add_all([self.user, self.admin])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.admin)

        app = FastAPI()
        app.include_router(auth_router, prefix="/api/auth")

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.settings_patch = patch(
            "app.services.auth_throttle.get_settings",
            return_value=_throttle_settings(),
        )
        self.mfa_settings_patch = patch(
            "app.services.admin_mfa.get_settings",
            return_value=_throttle_settings(),
        )
        self.whatsapp_patch = patch(
            "app.services.whatsapp.get_settings",
            return_value=_throttle_settings(whatsapp_enabled=False),
        )
        self.email_patch = patch(
            "app.services.mailer.get_settings",
            return_value=_throttle_settings(email_otp_enabled=False),
        )
        self.cookie_env = patch(
            "app.auth.get_settings",
            return_value=SimpleNamespace(app_environment="development", secret_key="k" * 40),
        )
        self.session_settings = patch(
            "app.services.auth_sessions.get_settings",
            return_value=SimpleNamespace(
                secret_key="k" * 40,
                auth_access_minutes=15,
                auth_refresh_hours=12,
                app_environment="development",
            ),
        )
        self.settings_patch.start()
        self.mfa_settings_patch.start()
        self.whatsapp_patch.start()
        self.email_patch.start()
        self.cookie_env.start()
        self.session_settings.start()

    def tearDown(self) -> None:
        self.session_settings.stop()
        self.cookie_env.stop()
        self.email_patch.stop()
        self.whatsapp_patch.stop()
        self.settings_patch.stop()
        self.mfa_settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _login(self, phone: str, password: str):
        return self.client.post(
            "/api/auth/login",
            data={"username": phone, "password": password},
        )

    def test_login_success_for_regular_user(self) -> None:
        res = self._login(self.user.phone, self.password)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["access_token"])
        self.assertTrue(body["authenticated"])
        self.assertFalse(body.get("mfa_required"))
        cookie = res.headers.get("set-cookie") or ""
        self.assertIn("cyberhost_sid=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertRegex(cookie, r"(?i)samesite=lax")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["phone"], self.user.phone)

    def test_login_success_with_email(self) -> None:
        res = self._login("Cliente@Example.com", self.password)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["authenticated"])
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "cliente@example.com")

    def test_login_email_unknown_same_error(self) -> None:
        res = self._login("naoexiste@example.com", self.password)
        self.assertEqual(res.status_code, 401)
        self.assertIn("e-mail", res.json()["detail"].lower())

    def test_failed_logins_get_backoff(self) -> None:
        with patch("app.api.auth.verify_password", return_value=False):
            first = self._login(self.user.phone, "wrong")
            second = self._login(self.user.phone, "wrong")
            third = self._login(self.user.phone, "wrong")
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(third.status_code, 429)
        self.assertIn("Muitas tentativas", third.json()["detail"])

    def test_register_locks_after_max_per_ip(self) -> None:
        self.settings_patch.stop()
        self.settings_patch = patch(
            "app.services.auth_throttle.get_settings",
            return_value=_throttle_settings(auth_register_ip_max=2),
        )
        self.settings_patch.start()
        created = []
        for index in range(3):
            res = self.client.post(
                "/api/auth/register",
                json={
                    "phone": f"1197777000{index}",
                    "email": f"user{index}@example.com",
                    "name": f"User {index}",
                    "password": "password1",
                },
            )
            created.append(res.status_code)
        self.assertEqual(created[0], 201)
        self.assertEqual(created[1], 201)
        self.assertEqual(created[2], 429)

    def test_register_requires_email(self) -> None:
        res = self.client.post(
            "/api/auth/register",
            json={"phone": "11977771111", "name": "Sem Email", "password": "password1"},
        )
        self.assertEqual(res.status_code, 422)

    def test_register_rejects_duplicate_email(self) -> None:
        first = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771112",
                "email": "dup@example.com",
                "name": "Um",
                "password": "password1",
            },
        )
        second = self.client.post(
            "/api/auth/register",
            json={
                "phone": "11977771113",
                "email": "DUP@example.com",
                "name": "Dois",
                "password": "password1",
            },
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertIn("E-mail", second.json()["detail"])

    def test_profile_update_changes_contact_and_password(self) -> None:
        self._login(self.user.phone, self.password)
        res = self.client.patch(
            "/api/auth/me",
            json={
                "name": "Cliente Atualizado",
                "email": "cliente@example.com",
                "phone": "11988880009",
                "current_password": self.password,
                "new_password": "new-horse-1",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["name"], "Cliente Atualizado")
        self.assertEqual(body["email"], "cliente@example.com")
        self.assertEqual(body["phone"], "11988880009")
        self.client.post("/api/auth/logout")
        old = self._login("11988880001", self.password)
        self.assertEqual(old.status_code, 401)
        new = self._login("11988880009", "new-horse-1")
        self.assertEqual(new.status_code, 200)

    def test_profile_update_rejects_wrong_password(self) -> None:
        self._login(self.user.phone, self.password)
        res = self.client.patch(
            "/api/auth/me",
            json={
                "name": self.user.name,
                "email": "cliente@example.com",
                "phone": self.user.phone,
                "current_password": "wrong-password",
            },
        )
        self.assertEqual(res.status_code, 403)

    def test_admin_must_enroll_and_verify_mfa(self) -> None:
        first = self._login(self.admin.phone, self.password)
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertTrue(body["mfa_setup_required"])
        self.assertTrue(body["mfa_ticket"])
        self.assertTrue(body["mfa_secret"])
        self.assertFalse(body["access_token"])

        bad = self.client.post(
            "/api/auth/mfa/verify",
            json={"ticket": body["mfa_ticket"], "code": "000000"},
        )
        self.assertEqual(bad.status_code, 401)

        code = totp_code(body["mfa_secret"])
        ok = self.client.post(
            "/api/auth/mfa/verify",
            json={"ticket": body["mfa_ticket"], "code": code},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(ok.json()["access_token"])
        self.assertTrue(ok.json()["authenticated"])

        self.db.refresh(self.admin)
        self.assertTrue(self.admin.mfa_enabled)

        second = self._login(self.admin.phone, self.password)
        self.assertTrue(second.json()["mfa_required"])
        self.assertFalse(second.json()["mfa_setup_required"])
        challenge = second.json()["mfa_ticket"]
        secret_plain = None
        from app.services.admin_mfa import decrypt_secret

        secret_plain = decrypt_secret(self.admin.mfa_secret)
        done = self.client.post(
            "/api/auth/mfa/verify",
            json={"ticket": challenge, "code": totp_code(secret_plain)},
        )
        self.assertEqual(done.status_code, 200)
        self.assertFalse(done.json()["access_token"])
        self.assertTrue(done.json()["authenticated"])

    def test_admin_skips_mfa_when_disabled(self) -> None:
        self.mfa_settings_patch.stop()
        self.mfa_settings_patch = patch(
            "app.services.admin_mfa.get_settings",
            return_value=_throttle_settings(admin_mfa_required=False),
        )
        self.mfa_settings_patch.start()
        res = self._login(self.admin.phone, self.password)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["authenticated"])
        self.assertFalse(body.get("mfa_required"))
        self.assertFalse(body.get("mfa_setup_required"))
        self.assertFalse(body.get("mfa_ticket"))
        cookie = res.headers.get("set-cookie") or ""
        self.assertIn("cyberhost_sid=", cookie)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["is_admin"])
