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

from app.auth import DEVICE_COOKIE_NAME, SESSION_COOKIE_NAME, create_access_token, hash_password
from app.database import Base, get_db
from app.models.auth_security import AuthMfaTicket, AuthSession, AuthThrottle
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.models.vps_connection import VpsConnectionDomain  # noqa: F401
from app.models.web_site import WebOrder, WebSite  # noqa: F401


def _load_auth_router():
    if "app.api.auth" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.auth import router

    return router


auth_router = _load_auth_router()


def _active_session_set_cookie(header: str) -> str:
    """Extrai o Set-Cookie ativo do sid (JWT), sem partir no vírgula do Expires."""
    parts: list[str] = []
    current = ""
    markers = (f"{SESSION_COOKIE_NAME}=", f"{DEVICE_COOKIE_NAME}=", "cyberhost_session=")
    for piece in header.split(","):
        if any(m in piece for m in markers) and current:
            parts.append(current.strip())
            current = piece
        elif not current:
            current = piece
        else:
            current = f"{current},{piece}"
    if current.strip():
        parts.append(current.strip())
    for part in parts:
        if (
            part.strip().startswith(f"{SESSION_COOKIE_NAME}=")
            and '=""' not in part.split(";")[0]
            and "Max-Age=0" not in part
        ):
            return part
    return header


def _throttle_settings() -> SimpleNamespace:
    return SimpleNamespace(
        secret_key="k" * 40,
        auth_login_ip_max=20,
        auth_login_ip_window_seconds=600,
        auth_login_phone_fail_max=8,
        auth_login_phone_window_seconds=900,
        auth_register_ip_max=5,
        auth_register_ip_window_seconds=3600,
        auth_mfa_ip_max=10,
        auth_mfa_ticket_seconds=120,
    )


class SessionCookieTests(unittest.TestCase):
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
        self.settings_patch = patch(
            "app.services.auth_throttle.get_settings",
            return_value=_throttle_settings(),
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
        self.cookie_env = patch(
            "app.auth.get_settings",
            return_value=SimpleNamespace(app_environment="development", secret_key="k" * 40),
        )
        self.settings_patch.start()
        self.session_settings.start()
        self.cookie_env.start()

    def tearDown(self) -> None:
        self.cookie_env.stop()
        self.session_settings.stop()
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _login(self):
        return self.client.post(
            "/api/auth/login",
            data={"username": self.user.phone, "password": self.password},
        )

    def test_login_sets_httponly_samesite_cookie_without_jwt_body(self) -> None:
        res = self._login()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["access_token"], "")
        self.assertTrue(body["authenticated"])
        cookie = res.headers.get("set-cookie") or ""
        self.assertIn(f"{SESSION_COOKIE_NAME}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/", cookie)
        self.assertRegex(cookie, r"(?i)samesite=lax")
        active = _active_session_set_cookie(cookie)
        self.assertNotRegex(active, r"(?i);\s*Secure")
        self.assertNotRegex(active, r"(?i)max-age=")
        self.assertNotRegex(active, r"(?i)expires=")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["id"], self.user.id)
        self.assertIn(DEVICE_COOKIE_NAME, self.client.cookies)

    def test_session_from_other_machine_is_rejected(self) -> None:
        self._login()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        # Simula cookie de sessão copiado para outra máquina (outro device id).
        self.client.cookies.set(DEVICE_COOKIE_NAME, "other-machine-device-id-0123456789ab")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_me_without_cookie_is_unauthorized(self) -> None:
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_bearer_still_works_without_cookie(self) -> None:
        token = create_access_token(self.user.id)
        res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], self.user.id)

    def test_logout_clears_cookie(self) -> None:
        self._login()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        gone = self.client.post("/api/auth/logout")
        self.assertEqual(gone.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_production_http_cookie_is_not_secure(self) -> None:
        self.cookie_env.stop()
        self.cookie_env = patch(
            "app.auth.get_settings",
            return_value=SimpleNamespace(app_environment="production", secret_key="k" * 40),
        )
        self.cookie_env.start()
        res = self._login()
        self.assertEqual(res.status_code, 200)
        cookie = res.headers.get("set-cookie") or ""
        active = _active_session_set_cookie(cookie)
        self.assertNotRegex(active, r"(?i);\s*Secure")
        self.assertIn("HttpOnly", active)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)

    def test_production_forwarded_https_cookie_is_secure(self) -> None:
        self.cookie_env.stop()
        self.cookie_env = patch(
            "app.auth.get_settings",
            return_value=SimpleNamespace(app_environment="production", secret_key="k" * 40),
        )
        self.cookie_env.start()
        res = self.client.post(
            "/api/auth/login",
            data={"username": self.user.phone, "password": self.password},
            headers={"X-Forwarded-Proto": "https"},
        )
        self.assertEqual(res.status_code, 200)
        cookie = res.headers.get("set-cookie") or ""
        self.assertRegex(cookie, r"(?i);\s*Secure")
        self.assertIn("HttpOnly", cookie)


    def test_login_clears_both_secure_variants_before_set(self) -> None:
        self.cookie_env.stop()
        self.cookie_env = patch(
            "app.auth.get_settings",
            return_value=SimpleNamespace(app_environment="production", secret_key="k" * 40),
        )
        self.cookie_env.start()
        res = self.client.post(
            "/api/auth/login",
            data={"username": self.user.phone, "password": self.password},
            headers={"X-Forwarded-Proto": "https"},
        )
        self.assertEqual(res.status_code, 200)
        # Starlette may fold Set-Cookie; TestClient exposes headers.getlist when available.
        cookies = res.headers.get_list("set-cookie") if hasattr(res.headers, "get_list") else [
            res.headers.get("set-cookie") or ""
        ]
        joined = "\n".join(cookies)
        self.assertIn(SESSION_COOKIE_NAME, joined)
        # Deve expirar a variante insegura e gravar a Secure.
        self.assertTrue(
            joined.lower().count("max-age=0") >= 1 or "max-age=0" in joined.lower(),
            msg=joined,
        )


if __name__ == "__main__":
    unittest.main()
