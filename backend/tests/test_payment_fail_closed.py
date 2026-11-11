import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings
from app.services.abacatepay import AbacatePayService


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_environment": "development",
        "abacatepay_enabled": False,
        "abacatepay_api_key": "",
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


class PaymentFailClosedTests(unittest.TestCase):
    def test_disabled_provider_does_not_create_test_charges(self) -> None:
        pay = AbacatePayService(_settings())
        self.assertTrue(pay.payments_required)
        self.assertFalse(pay.payment_bypass_enabled)
        with self.assertRaises(HTTPException) as raised:
            pay.create_checkout(1, 1990, "11999999999", "VPS")
        self.assertEqual(raised.exception.status_code, 503)

    def test_development_bypass_still_allows_test_mode(self) -> None:
        pay = AbacatePayService(_settings(skip_payment_for_testing=True))
        self.assertFalse(pay.payments_required)
        result = pay.create_checkout(2, 1990, "11999999999", "VPS")
        self.assertEqual(result.status, "test_mode")

    def test_production_rejects_payment_bypass(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(
                app_environment="production",
                skip_payment_for_testing=True,
                abacatepay_enabled=True,
                abacatepay_api_key="a" * 40,
            )

    def test_production_requires_live_provider(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(app_environment="production", abacatepay_enabled=False)


if __name__ == "__main__":
    unittest.main()
