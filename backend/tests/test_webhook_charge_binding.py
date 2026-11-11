import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.config import Settings
from app.services.abacatepay import (
    ORDER_KIND_GAME,
    ORDER_KIND_VPS,
    ORDER_KIND_WEB,
    AbacatePayService,
)


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_environment": "development",
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


def _order(**overrides) -> SimpleNamespace:
    values = {
        "id": 12,
        "payment_external_id": "pix_char_abc123",
        "total_cents": 1990,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _paid_charge(**overrides) -> dict:
    values = {
        "id": "pix_char_abc123",
        "status": "PAID",
        "amount": 1990,
        "currency": "BRL",
        "devMode": False,
        "metadata": {"order_id": "12", "customer_phone": "11999999999"},
    }
    values.update(overrides)
    return values


class WebhookChargeBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pay = AbacatePayService(_settings())

    def test_extract_charge_id_ignores_webhook_log_id(self) -> None:
        payload = {
            "id": "log_abc123xyz",
            "event": "transparent.completed",
            "data": {"id": "pix_char_abc123", "status": "PAID"},
        }
        self.assertEqual(
            AbacatePayService.extract_charge_id(payload),
            "pix_char_abc123",
        )

    def test_extract_charge_id_rejects_envelope_without_data(self) -> None:
        payload = {"id": "pix_char_abc123", "event": "transparent.completed"}
        self.assertIsNone(AbacatePayService.extract_charge_id(payload))

    def test_matching_provider_charge_is_accepted(self) -> None:
        order = _order()
        with patch.object(self.pay, "get_transparent", return_value=_paid_charge()):
            self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
            self.assertTrue(self.pay.order_is_paid_at_provider(order, ORDER_KIND_VPS))

    def test_amount_mismatch_is_rejected(self) -> None:
        order = _order(total_cents=5000)
        with patch.object(self.pay, "get_transparent", return_value=_paid_charge()):
            with self.assertRaises(HTTPException) as raised:
                self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
            self.assertEqual(raised.exception.status_code, 409)
            self.assertFalse(self.pay.order_is_paid_at_provider(order, ORDER_KIND_VPS))

    def test_metadata_mismatch_is_rejected(self) -> None:
        order = _order()
        charge = _paid_charge(metadata={"order_id": "99"})
        with patch.object(self.pay, "get_transparent", return_value=charge):
            with self.assertRaises(HTTPException) as raised:
                self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 409)

    def test_pending_status_is_rejected(self) -> None:
        order = _order()
        with patch.object(self.pay, "get_transparent", return_value=_paid_charge(status="PENDING")):
            with self.assertRaises(HTTPException) as raised:
                self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 409)

    def test_currency_mismatch_is_rejected(self) -> None:
        order = _order()
        with patch.object(self.pay, "get_transparent", return_value=_paid_charge(currency="USD")):
            with self.assertRaises(HTTPException) as raised:
                self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 409)

    def test_production_rejects_dev_mode_charge(self) -> None:
        pay = AbacatePayService(_settings(app_environment="production"))
        order = _order()
        with patch.object(pay, "get_transparent", return_value=_paid_charge(devMode=True)):
            with self.assertRaises(HTTPException) as raised:
                pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 409)

    def test_production_allow_dev_mode_flag_accepts_sandbox_charge(self) -> None:
        pay = AbacatePayService(_settings(app_environment="production"))
        order = _order()
        charge = _paid_charge(devMode=True)
        pay.assert_paid_charge(
            charge,
            expected_id=order.payment_external_id,
            expected_amount_cents=order.total_cents,
            expected_kind=ORDER_KIND_VPS,
            expected_order_id=order.id,
            allow_dev_mode=True,
        )

    def test_extract_charge_payload_copies_envelope_dev_mode(self) -> None:
        payload = AbacatePayService.extract_charge_payload(
            {
                "success": True,
                "devMode": True,
                "data": {"id": "pix_char_abc123", "status": "PENDING"},
            }
        )
        self.assertTrue(payload["devMode"])
        self.assertEqual(payload["status"], "PENDING")
        self.assertFalse(AbacatePayService.is_explicit_live_charge(payload))
        self.assertFalse(
            AbacatePayService.is_explicit_live_charge({"id": "pix_char_abc123", "status": "PENDING"})
        )
        self.assertTrue(AbacatePayService.is_explicit_live_charge({"devMode": False}))

    def test_webhook_amount_fills_sparse_provider_check(self) -> None:
        order = _order()
        payload = {
            "id": "log_abc",
            "event": "transparent.completed",
            "devMode": False,
            "data": _paid_charge(),
        }
        with patch.object(
            self.pay,
            "get_transparent",
            return_value={"id": "pix_char_abc123", "status": "PAID"},
        ):
            self.pay.verify_paid_charge_for_order(
                order,
                ORDER_KIND_VPS,
                webhook_payload=payload,
            )

    def test_metadata_only_payload_does_not_bind_a_charge(self) -> None:
        payload = {
            "event": "transparent.completed",
            "metadata": {"order_id": "12"},
            "data": {"order_id": "12", "status": "PAID"},
        }
        self.assertIsNone(AbacatePayService.extract_charge_id(payload))

    def test_test_charge_ids_are_not_usable(self) -> None:
        self.assertFalse(AbacatePayService.is_usable_charge_id("test-12"))
        self.assertFalse(AbacatePayService.is_usable_charge_id("free-12"))
        self.assertFalse(AbacatePayService.is_usable_charge_id("log_abc"))
        order = _order(payment_external_id="test-12")
        with self.assertRaises(HTTPException) as raised:
            self.pay.verify_paid_charge_for_order(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 409)

    def test_game_metadata_key_is_required(self) -> None:
        order = _order()
        charge = _paid_charge(metadata={"game_order_id": "12"})
        with patch.object(self.pay, "get_transparent", return_value=charge):
            self.pay.verify_paid_charge_for_order(order, ORDER_KIND_GAME)

    def test_web_metadata_key_is_required(self) -> None:
        order = _order()
        charge = _paid_charge(metadata={"web_order_id": "12"})
        with patch.object(self.pay, "get_transparent", return_value=charge):
            self.pay.verify_paid_charge_for_order(order, ORDER_KIND_WEB)

    def test_provider_outage_is_not_swallowed(self) -> None:
        order = _order()
        with patch.object(
            self.pay,
            "get_transparent",
            side_effect=HTTPException(status_code=502, detail="Abacate Pay: down"),
        ):
            with self.assertRaises(HTTPException) as raised:
                self.pay.order_is_paid_at_provider(order, ORDER_KIND_VPS)
        self.assertEqual(raised.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
