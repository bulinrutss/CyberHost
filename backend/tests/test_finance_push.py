import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.finance_auth import create_finance_access_token, hash_password
from app.finance_database import FinanceBase, get_finance_db
from app.models.finance import (
    FinanceEvent,
    FinanceEventNotice,
    FinancePushSubscription,
)
from app.models.finance_user import FinanceUser
from app.services import finance_push


def _load_router():
    if "app.api.finance" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.finance import router

    return router


finance_router = _load_router()


class FinancePushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        FinanceBase.metadata.create_all(
            self.engine,
            tables=[
                FinanceUser.__table__,
                FinanceEvent.__table__,
                FinancePushSubscription.__table__,
                FinanceEventNotice.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = FinanceUser(
            phone="11988880011",
            email="ana-push@example.com",
            name="Ana",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
        )
        self.other = FinanceUser(
            phone="11988880012",
            email="bia-push@example.com",
            name="Bia",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other)

        app = FastAPI()
        app.include_router(finance_router, prefix="/api/finance")
        db = self.db

        def _override_db():
            yield db

        app.dependency_overrides[get_finance_db] = _override_db
        self.client = TestClient(app)
        self.settings = SimpleNamespace(
            finance_push_configured=True,
            vapid_public_key="B" + "x" * 86,
            vapid_private_pem="-----BEGIN PRIVATE KEY-----\\ntest\\n-----END PRIVATE KEY-----",
            vapid_subject="mailto:test@example.com",
            finance_timezone="America/Sao_Paulo",
            finance_event_lead_minutes=15,
        )
        self.settings_patch = patch("app.services.finance_push.get_settings", return_value=self.settings)
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _auth(self, user: FinanceUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_finance_access_token(user.id)}"}

    def test_subscribe_requires_auth_and_stays_private(self) -> None:
        payload = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/ana-device",
            "keys": {"p256dh": "p" * 32, "auth": "a" * 16},
        }
        anon = self.client.post("/api/finance/push/subscribe", json=payload)
        self.assertEqual(anon.status_code, 401)

        created = self.client.post(
            "/api/finance/push/subscribe",
            headers=self._auth(self.user),
            json=payload,
        )
        self.assertEqual(created.status_code, 204, created.text)

        stolen = self.client.post(
            "/api/finance/push/subscribe",
            headers=self._auth(self.other),
            json=payload,
        )
        self.assertEqual(stolen.status_code, 403)

        row = self.db.query(FinancePushSubscription).one()
        self.assertEqual(row.user_id, self.user.id)

    def test_notifies_timed_event_once(self) -> None:
        now = datetime(2026, 8, 31, 14, 0, 0)
        event = FinanceEvent(
            user_id=self.user.id,
            title="Dentista",
            category="saude",
            starts_at=now + timedelta(minutes=10),
            duration_min=45,
            all_day=False,
        )
        sub = FinancePushSubscription(
            user_id=self.user.id,
            endpoint="https://fcm.googleapis.com/fcm/send/ana-device",
            p256dh="p" * 32,
            auth="a" * 16,
        )
        self.db.add_all([event, sub])
        self.db.commit()
        self.db.refresh(event)

        with patch("app.services.finance_push._now_local", return_value=now), patch(
            "app.services.finance_push._send_one", return_value=True
        ) as send:
            first = finance_push.notify_due_events(self.db)
            second = finance_push.notify_due_events(self.db)
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.db.query(FinanceEventNotice).count(), 1)

    def test_other_user_event_is_not_sent_to_stranger(self) -> None:
        now = datetime(2026, 8, 31, 8, 10, 0)
        event = FinanceEvent(
            user_id=self.user.id,
            title="Particular",
            category="pessoal",
            starts_at=now.replace(hour=0, minute=0, second=0),
            duration_min=0,
            all_day=True,
        )
        stranger = FinancePushSubscription(
            user_id=self.other.id,
            endpoint="https://fcm.googleapis.com/fcm/send/bia-device",
            p256dh="p" * 32,
            auth="a" * 16,
        )
        self.db.add_all([event, stranger])
        self.db.commit()
        with patch("app.services.finance_push._now_local", return_value=now), patch(
            "app.services.finance_push._send_one", return_value=True
        ) as send:
            sent = finance_push.notify_due_events(self.db)
        self.assertEqual(sent, 0)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
