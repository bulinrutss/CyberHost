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

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.models.host_push import HostPushSubscription
from app.models.user import User
from app.services import host_notify, host_push


def _load_router():
    if "app.api.push" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.push import router

    return router


push_router = _load_router()


class HostPushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, HostPushSubscription.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11988880021",
            email="cliente-push@example.com",
            name="Cliente",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.admin = User(
            phone="11988880022",
            email="admin-push@example.com",
            name="Admin",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=True,
        )
        self.other = User(
            phone="11988880023",
            email="outro-push@example.com",
            name="Outro",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.db.add_all([self.user, self.admin, self.other])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.admin)
        self.db.refresh(self.other)

        app = FastAPI()
        app.include_router(push_router, prefix="/api/push")
        db = self.db

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(app)
        self.settings = SimpleNamespace(
            web_push_configured=True,
            vapid_public_key="B" + "x" * 86,
            vapid_private_pem="-----BEGIN PRIVATE KEY-----\\ntest\\n-----END PRIVATE KEY-----",
            vapid_subject="mailto:test@example.com",
        )
        self.settings_patch = patch("app.services.web_push.get_settings", return_value=self.settings)
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _auth(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    def _add_sub(self, user: User, token: str) -> HostPushSubscription:
        row = HostPushSubscription(
            user_id=user.id,
            endpoint=f"https://fcm.googleapis.com/fcm/send/{token}",
            p256dh="p" * 32,
            auth="a" * 16,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_subscribe_requires_auth_and_stays_private(self) -> None:
        payload = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/cliente-device",
            "keys": {"p256dh": "p" * 32, "auth": "a" * 16},
        }
        anon = self.client.post("/api/push/subscribe", json=payload)
        self.assertEqual(anon.status_code, 401)

        created = self.client.post(
            "/api/push/subscribe",
            headers=self._auth(self.user),
            json=payload,
        )
        self.assertEqual(created.status_code, 204, created.text)

        stolen = self.client.post(
            "/api/push/subscribe",
            headers=self._auth(self.other),
            json=payload,
        )
        self.assertEqual(stolen.status_code, 403)

        row = self.db.query(HostPushSubscription).one()
        self.assertEqual(row.user_id, self.user.id)

    def test_public_key_requires_login(self) -> None:
        anon = self.client.get("/api/push/public-key")
        self.assertEqual(anon.status_code, 401)
        ok = self.client.get("/api/push/public-key", headers=self._auth(self.user))
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["push_available"])
        self.assertEqual(ok.json()["vapid_public_key"], self.settings.vapid_public_key)

    def test_notify_user_does_not_reach_stranger(self) -> None:
        self._add_sub(self.user, "cliente")
        self._add_sub(self.other, "estranho")
        with patch("app.services.web_push.send", return_value=True) as send:
            sent = host_push.notify_user(
                self.db,
                self.user.id,
                title="Pagamento confirmado",
                body="VPS paga",
                url="/dashboard/orders",
                tag="pay-vps",
            )
        self.assertEqual(sent, 1)
        self.assertEqual(send.call_count, 1)
        self.assertIn("cliente", send.call_args.args[0])

    def test_notify_admins_skips_actor(self) -> None:
        self._add_sub(self.admin, "admin")
        self._add_sub(self.user, "cliente")
        with patch("app.services.web_push.send", return_value=True) as send:
            sent = host_push.notify_admins(
                self.db,
                title="Novo ticket",
                body="Cliente pediu ajuda",
                url="/admin?tab=support",
                tag="ticket-1",
                exclude_user_ids={self.admin.id},
            )
        self.assertEqual(sent, 0)
        send.assert_not_called()

    def test_new_ticket_notifies_admin_not_customer(self) -> None:
        self._add_sub(self.admin, "admin")
        self._add_sub(self.user, "cliente")
        with patch("app.services.web_push.send", return_value=True) as send:
            host_notify.on_new_ticket(
                self.db,
                ticket_id=9,
                subject="VPS offline",
                preview="Não liga",
                customer_user_id=self.user.id,
            )
        self.assertEqual(send.call_count, 1)
        self.assertIn("admin", send.call_args.args[0])

    def test_staff_reply_notifies_customer(self) -> None:
        self._add_sub(self.admin, "admin")
        self._add_sub(self.user, "cliente")
        with patch("app.services.web_push.send", return_value=True) as send:
            host_notify.on_ticket_message(
                self.db,
                ticket_id=9,
                subject="VPS offline",
                preview="Já olhamos",
                customer_user_id=self.user.id,
                author_id=self.admin.id,
                as_staff=True,
                assigned_admin_id=self.admin.id,
            )
        self.assertEqual(send.call_count, 1)
        self.assertIn("cliente", send.call_args.args[0])

    def test_payment_notifies_customer_and_admin(self) -> None:
        self._add_sub(self.admin, "admin")
        self._add_sub(self.user, "cliente")
        with patch("app.services.web_push.send", return_value=True) as send:
            host_notify.on_payment_confirmed(
                self.db,
                kind="CyberCloud",
                summary="CyberCloud +50 GB",
                total_cents=1990,
                customer_user_id=self.user.id,
                client_url="/dashboard/files",
            )
        endpoints = {call.args[0] for call in send.call_args_list}
        self.assertEqual(send.call_count, 2)
        self.assertTrue(any("cliente" in item for item in endpoints))
        self.assertTrue(any("admin" in item for item in endpoints))


if __name__ == "__main__":
    unittest.main()
