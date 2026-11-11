import unittest
from unittest.mock import MagicMock

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder, CloudStorageOrderStatus
from app.models.coupon import CouponRedemption, DiscountCoupon  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder, VpsPlan  # noqa: F401
from app.services.abacatepay import AbacatePayService
from app.services.pixdev import (
    extract_charge_ids,
    find_charge_ids_by_br_code,
    find_order,
    release_charge,
    release_text,
)


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_environment": "production",
        "abacatepay_enabled": True,
        "abacatepay_api_key": "a" * 40,
        "abacatepay_webhook_secret": "w" * 40,
        "skip_payment_for_testing": False,
        "secret_key": "k" * 40,
        "esxi_ssl_pin_sha256": "a" * 64,
        "frontend_url": "https://ruts.dev",
        "api_public_url": "https://ruts.dev",
        "cors_origins": "https://ruts.dev",
    }
    values.update(overrides)
    return Settings(**values)


class ExtractChargeIdsTests(unittest.TestCase):
    def test_extracts_from_br_code_url_and_raw_id(self) -> None:
        blob = (
            "00020126360014br.gov.bcb.pix0114pix_char_Aaa111520400005303986"
            "540549.905802BR5913CyberHost6009Sao Paulo"
            "\nhttps://pay.example/c/pix_char_Aaa111?x=1\n"
            "pix_char_Bbb222\n"
            "pix_char_Aaa111\n"
        )
        self.assertEqual(
            extract_charge_ids(blob),
            ["pix_char_Aaa111", "pix_char_Bbb222"],
        )
        self.assertEqual(
            extract_charge_ids("PIX_CHAR_CWg0XaUbyUHBH4RjbcZcXnrt"),
            ["pix_char_CWg0XaUbyUHBH4RjbcZcXnrt"],
        )
        wrapped = "pix_char_\nCWg0XaUbyUHBH4RjbcZcXnrt"
        self.assertEqual(
            extract_charge_ids(wrapped),
            ["pix_char_CWg0XaUbyUHBH4RjbcZcXnrt"],
        )
        self.assertEqual(
            extract_charge_ids(
                "00020126pix_char_TRXGEDm4phpg2PURAGRqgDzj520400005303986"
            ),
            ["pix_char_TRXGEDm4phpg2PURAGRqgDzj"],
        )

    def test_empty_and_limit(self) -> None:
        self.assertEqual(extract_charge_ids(""), [])
        many = " ".join(f"pix_char_Test{i:02d}" for i in range(25))
        self.assertEqual(len(extract_charge_ids(many, limit=3)), 3)


class PixDevReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                CloudStorageOrder.__table__,
                GameOrder.__table__,
                VpsPlan.__table__,
                VpsOrder.__table__,
                VpsInstance.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11988880001",
            name="Pix Dev",
            hashed_password="x",
            is_active=True,
            is_admin=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.tasks = BackgroundTasks()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _order(self, charge_id: str, **overrides) -> CloudStorageOrder:
        values = {
            "user_id": self.user.id,
            "extra_gb": 50,
            "renewal_months": None,
            "total_cents": 1990,
            "status": CloudStorageOrderStatus.PENDING_PAYMENT,
            "payment_external_id": charge_id,
        }
        values.update(overrides)
        order = CloudStorageOrder(**values)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def _pay(self, charge: dict, *, simulate: bool = False) -> AbacatePayService:
        pay = AbacatePayService(_settings())
        pending = dict(charge)
        paid = dict(charge)
        paid["status"] = "PAID"
        if simulate:
            def fetch(_cid: str) -> dict:
                if pay.simulate_sandbox_payment.called:
                    return dict(paid)
                return dict(pending)

            pay.fetch_charge = MagicMock(side_effect=fetch)
            pay.simulate_sandbox_payment = MagicMock(return_value={"status": "PAID"})
        else:
            pay.fetch_charge = MagicMock(return_value=dict(charge))
            pay.simulate_sandbox_payment = MagicMock()
        return pay

    def test_finds_cloud_order_by_charge_id(self) -> None:
        order = self._order("pix_char_cloud1")
        kind, found = find_order(self.db, "pix_char_cloud1")
        self.assertEqual(kind, "cloud")
        self.assertEqual(found.id, order.id)

    def test_release_simulates_dev_mode_and_credits(self) -> None:
        order = self._order("pix_char_cloud2")
        pay = self._pay(
            {
                "id": "pix_char_cloud2",
                "status": "PENDING",
                "amount": 1990,
                "currency": "BRL",
                "devMode": True,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            },
            simulate=True,
        )
        result = release_charge(self.db, "pix_char_cloud2", self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "released")
        self.assertTrue(result.simulated)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)
        pay.simulate_sandbox_payment.assert_called_once_with("pix_char_cloud2")

    def test_already_paid_is_skipped(self) -> None:
        self._order("pix_char_cloud3", status=CloudStorageOrderStatus.PAID)
        result = release_charge(self.db, "pix_char_cloud3", self.tasks, pay=MagicMock())
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "already")

    def test_live_charge_is_rejected_without_simulate(self) -> None:
        order = self._order("pix_char_live1")
        pay = self._pay(
            {
                "id": "pix_char_live1",
                "status": "PENDING",
                "amount": 1990,
                "currency": "BRL",
                "devMode": False,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            }
        )
        result = release_charge(self.db, "pix_char_live1", self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "failed")
        self.assertEqual(order.status, CloudStorageOrderStatus.PENDING_PAYMENT)
        pay.simulate_sandbox_payment.assert_not_called()

    def test_unknown_charge_fails(self) -> None:
        result = release_charge(self.db, "pix_char_missing", self.tasks, pay=MagicMock())
        self.assertFalse(result.ok)
        self.assertEqual(result.detail, "Pedido não encontrado")

    def test_release_text_requires_pix_char(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            release_text(self.db, "codigo copia e cola sem id", self.tasks)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("pix_char_", raised.exception.detail)

    def test_release_text_accepts_copia_e_cola_without_charge_id(self) -> None:
        br_code = (
            "00020126580014br.gov.bcb.pix0136"
            + ("a" * 36)
            + "52040000530398654040.105802BR5909CyberHost6304AAAA"
        )
        self.assertNotIn("pix_char_", br_code)
        order = self._order("pix_char_frombr1", pix_br_code=br_code)
        self.assertEqual(find_charge_ids_by_br_code(self.db, br_code), ["pix_char_frombr1"])
        wrapped = " ".join(br_code[i : i + 32] for i in range(0, len(br_code), 32))
        self.assertEqual(find_charge_ids_by_br_code(self.db, wrapped), ["pix_char_frombr1"])
        pay = self._pay(
            {
                "id": "pix_char_frombr1",
                "status": "PAID",
                "amount": 1990,
                "currency": "BRL",
                "devMode": True,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            }
        )
        results = release_text(self.db, wrapped, self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)

    def test_amount_mismatch_does_not_credit(self) -> None:
        order = self._order("pix_char_amt")
        pay = self._pay(
            {
                "id": "pix_char_amt",
                "status": "PAID",
                "amount": 1,
                "currency": "BRL",
                "devMode": True,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            }
        )
        result = release_charge(self.db, "pix_char_amt", self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertFalse(result.ok)
        self.assertEqual(result.detail, "Valor da cobrança não confere")
        self.assertEqual(order.status, CloudStorageOrderStatus.PENDING_PAYMENT)

    def test_paid_dev_mode_credits_in_production_settings(self) -> None:
        order = self._order("pix_char_flag")
        pay = self._pay(
            {
                "id": "pix_char_flag",
                "status": "PAID",
                "amount": 1990,
                "currency": "BRL",
                "devMode": True,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            }
        )
        result = release_charge(self.db, "pix_char_flag", self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "released")
        self.assertFalse(result.simulated)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)

    def test_sparse_check_without_devmode_still_simulates(self) -> None:
        order = self._order("pix_char_sparse")
        pay = AbacatePayService(_settings())
        pay.fetch_charge = MagicMock(
            return_value={
                "id": "pix_char_sparse",
                "status": "PENDING",
                "expiresAt": "2026-09-01T00:00:00.000Z",
            }
        )
        pay.simulate_sandbox_payment = MagicMock(
            return_value={
                "id": "pix_char_sparse",
                "status": "PAID",
                "amount": 1990,
                "currency": "BRL",
                "devMode": True,
                "metadata": {"cloud_storage_order_id": str(order.id)},
            }
        )
        result = release_charge(self.db, "pix_char_sparse", self.tasks, pay=pay)
        self.db.refresh(order)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "released")
        self.assertTrue(result.simulated)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)
        pay.simulate_sandbox_payment.assert_called_once_with("pix_char_sparse")


if __name__ == "__main__":
    unittest.main()
