import sys
import tempfile
import types
import unittest
from datetime import date, datetime, timedelta
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
from app.models.finance import FinanceEvent, FinanceEventNotice, FinanceGoal, FinanceTransaction
from app.models.finance_user import FinanceUser


def _load_router():
    if "app.api.finance" not in sys.modules:
        dummy = types.ModuleType("app.api")
        dummy.__path__ = [str(Path(__file__).resolve().parents[1] / "app" / "api")]
        dummy.__package__ = "app.api"
        sys.modules.setdefault("app.api", dummy)
    from app.api.finance import router

    return router


finance_router = _load_router()


class FinanceApiTests(unittest.TestCase):
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
                FinanceTransaction.__table__,
                FinanceEvent.__table__,
                FinanceEventNotice.__table__,
                FinanceGoal.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = FinanceUser(
            phone="11988880001",
            email="ana@example.com",
            name="Ana",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
        )
        self.other = FinanceUser(
            phone="11988880002",
            email="bia@example.com",
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
        self.receipts_dir = tempfile.TemporaryDirectory()
        self.receipts_patch = patch(
            "app.services.finance_receipts.get_settings",
            return_value=SimpleNamespace(
                finance_receipts_path=self.receipts_dir.name,
                finance_receipt_max_bytes=8 * 1024 * 1024,
            ),
        )
        self.receipts_patch.start()

    def tearDown(self) -> None:
        self.receipts_patch.stop()
        self.receipts_dir.cleanup()
        self.db.close()
        self.engine.dispose()

    def _auth(self, user: FinanceUser) -> dict[str, str]:
        token = create_finance_access_token(user.id)
        return {"Authorization": f"Bearer {token}"}

    def test_meta_is_public(self) -> None:
        res = self.client.get("/api/finance/meta")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["income_categories"])
        self.assertTrue(body["expense_categories"])
        self.assertTrue(body["event_categories"])

    def test_stats_requires_auth(self) -> None:
        res = self.client.get("/api/finance/stats")
        self.assertEqual(res.status_code, 401)

    def test_create_income_and_expense_and_stats(self) -> None:
        today = date.today().isoformat()
        income = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "income",
                "title": "Salário",
                "amount_cents": 500000,
                "category": "salario",
                "payment_method": "ted",
                "notes": "CLT",
                "occurred_on": today,
            },
        )
        self.assertEqual(income.status_code, 201, income.text)
        expense = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "expense",
                "title": "Dentista",
                "amount_cents": 25000,
                "category": "saude",
                "payment_method": "pix",
                "notes": "Consulta",
                "occurred_on": today,
            },
        )
        self.assertEqual(expense.status_code, 201, expense.text)

        stats = self.client.get("/api/finance/stats", headers=self._auth(self.user))
        self.assertEqual(stats.status_code, 200)
        body = stats.json()
        self.assertEqual(body["income_cents"], 500000)
        self.assertEqual(body["expense_cents"], 25000)
        self.assertEqual(body["balance_cents"], 475000)
        self.assertEqual(body["all_time_balance_cents"], 475000)
        self.assertEqual(body["transaction_count"], 2)
        self.assertTrue(any(item["id"] == "saude" for item in body["by_category"]))

    def test_user_cannot_see_or_edit_another_users_data(self) -> None:
        created = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "expense",
                "title": "Aluguel",
                "amount_cents": 120000,
                "category": "moradia",
                "occurred_on": date.today().isoformat(),
            },
        )
        tx_id = created.json()["id"]

        listed = self.client.get("/api/finance/transactions", headers=self._auth(self.other))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), [])

        patched = self.client.patch(
            f"/api/finance/transactions/{tx_id}",
            headers=self._auth(self.other),
            json={"title": "hack"},
        )
        self.assertEqual(patched.status_code, 404)

        deleted = self.client.delete(
            f"/api/finance/transactions/{tx_id}",
            headers=self._auth(self.other),
        )
        self.assertEqual(deleted.status_code, 404)

        still = self.client.get("/api/finance/transactions", headers=self._auth(self.user))
        self.assertEqual(len(still.json()), 1)

    def test_rejects_incompatible_category(self) -> None:
        res = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "expense",
                "title": "Salário invertido",
                "amount_cents": 1000,
                "category": "salario",
                "occurred_on": date.today().isoformat(),
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_event_crud_and_isolation(self) -> None:
        starts = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
        created = self.client.post(
            "/api/finance/events",
            headers=self._auth(self.user),
            json={
                "title": "Dentista",
                "category": "saude",
                "notes": "Limpeza",
                "starts_at": starts.isoformat(),
                "duration_min": 45,
                "all_day": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        event_id = created.json()["id"]
        self.assertEqual(created.json()["duration_min"], 45)

        other_list = self.client.get("/api/finance/events", headers=self._auth(self.other))
        self.assertEqual(other_list.json(), [])

        patched = self.client.patch(
            f"/api/finance/events/{event_id}",
            headers=self._auth(self.user),
            json={"all_day": True},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertTrue(patched.json()["all_day"])
        self.assertEqual(patched.json()["duration_min"], 0)

        deleted = self.client.delete(
            f"/api/finance/events/{event_id}",
            headers=self._auth(self.other),
        )
        self.assertEqual(deleted.status_code, 404)

        gone = self.client.delete(
            f"/api/finance/events/{event_id}",
            headers=self._auth(self.user),
        )
        self.assertEqual(gone.status_code, 204)

    def test_allows_empty_title(self) -> None:
        res = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "income",
                "title": "   ",
                "amount_cents": 1000,
                "category": "outro",
                "occurred_on": date.today().isoformat(),
            },
        )
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["title"], "")
        self.assertFalse(res.json()["has_receipt"])

    def test_goal_progress_and_isolation(self) -> None:
        created = self.client.post(
            "/api/finance/goals",
            headers=self._auth(self.user),
            json={
                "title": "Viagem",
                "target_cents": 100000,
                "saved_cents": 20000,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["remaining_cents"], 80000)
        self.assertEqual(body["progress_percent"], 20)
        goal_id = body["id"]

        listed = self.client.get("/api/finance/goals", headers=self._auth(self.other))
        self.assertEqual(listed.json(), [])

        deposited = self.client.post(
            f"/api/finance/goals/{goal_id}/deposit",
            headers=self._auth(self.user),
            json={"amount_cents": 10000},
        )
        self.assertEqual(deposited.status_code, 200)
        self.assertEqual(deposited.json()["saved_cents"], 30000)

        blocked = self.client.delete(
            f"/api/finance/goals/{goal_id}",
            headers=self._auth(self.other),
        )
        self.assertEqual(blocked.status_code, 404)

    def test_receipt_upload_and_isolation(self) -> None:
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
        created = self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "expense",
                "amount_cents": 2590,
                "category": "alimentacao",
                "occurred_on": date.today().isoformat(),
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        tx_id = created.json()["id"]

        uploaded = self.client.post(
            f"/api/finance/transactions/{tx_id}/receipt",
            headers=self._auth(self.user),
            files={"file": ("nota.png", png, "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertTrue(uploaded.json()["has_receipt"])
        self.assertEqual(uploaded.json()["receipt_ext"], "png")

        other = self.client.get(
            f"/api/finance/transactions/{tx_id}/receipt",
            headers=self._auth(self.other),
        )
        self.assertEqual(other.status_code, 404)

        mine = self.client.get(
            f"/api/finance/transactions/{tx_id}/receipt",
            headers=self._auth(self.user),
        )
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.content[:8], b"\x89PNG\r\n\x1a\n")

        rejected = self.client.post(
            f"/api/finance/transactions/{tx_id}/receipt",
            headers=self._auth(self.user),
            files={"file": ("nota.txt", b"not-an-image", "text/plain")},
        )
        self.assertEqual(rejected.status_code, 400)

    def test_filters_by_period_kind_and_payment_method(self) -> None:
        today = date.today()
        last_month = (today.replace(day=1) - timedelta(days=1)).isoformat()
        self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "income",
                "amount_cents": 10000,
                "category": "salario",
                "payment_method": "ted",
                "occurred_on": today.isoformat(),
            },
        )
        self.client.post(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            json={
                "kind": "expense",
                "amount_cents": 2500,
                "category": "alimentacao",
                "payment_method": "pix",
                "occurred_on": last_month,
            },
        )
        month = self.client.get(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            params={"start": today.replace(day=1).isoformat(), "end": today.isoformat(), "kind": "income"},
        )
        self.assertEqual(month.status_code, 200)
        self.assertEqual(len(month.json()), 1)
        self.assertEqual(month.json()[0]["kind"], "income")

        pix = self.client.get(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            params={"payment_method": "pix"},
        )
        self.assertEqual(pix.status_code, 200)
        self.assertEqual(len(pix.json()), 1)
        self.assertEqual(pix.json()[0]["payment_method"], "pix")

        bad = self.client.get(
            "/api/finance/transactions",
            headers=self._auth(self.user),
            params={"payment_method": "cheque"},
        )
        self.assertEqual(bad.status_code, 400)

    def test_monthly_goal_requires_due_day_and_rolls(self) -> None:
        missing = self.client.post(
            "/api/finance/goals",
            headers=self._auth(self.user),
            json={"title": "Reserva", "kind": "monthly", "target_cents": 50000},
        )
        self.assertEqual(missing.status_code, 422)

        created = self.client.post(
            "/api/finance/goals",
            headers=self._auth(self.user),
            json={
                "title": "Reserva",
                "kind": "monthly",
                "target_cents": 50000,
                "saved_cents": 10000,
                "due_day": 10,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["kind"], "monthly")
        self.assertEqual(body["due_day"], 10)
        self.assertEqual(body["saved_cents"], 10000)
        self.assertIsNotNone(body["due_on"])
        due = date.fromisoformat(body["due_on"])
        today = date.today()
        self.assertEqual(due.year, today.year)
        self.assertEqual(due.month, today.month)
        self.assertEqual(due.day, 10)

        row = self.db.get(FinanceGoal, body["id"])
        assert row is not None
        row.period_year = date.today().year - 1
        row.period_month = 12
        row.saved_cents = 10000
        self.db.commit()

        listed = self.client.get("/api/finance/goals", headers=self._auth(self.user))
        self.assertEqual(listed.status_code, 200)
        rolled = next(item for item in listed.json() if item["id"] == body["id"])
        self.assertEqual(rolled["saved_cents"], 0)
        self.assertEqual(rolled["kind"], "monthly")


if __name__ == "__main__":
    unittest.main()
