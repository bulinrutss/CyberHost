import base64
import hashlib
import hmac
import unittest

from fastapi import HTTPException

from app.config import Settings
from app.services.abacatepay import ABACATEPAY_PUBLIC_KEY, AbacatePayService


class WebhookAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "w" * 40
        self.body = b'{"event":"transparent.completed"}'
        self.pay = AbacatePayService(
            Settings(
                _env_file=None,
                abacatepay_enabled=True,
                abacatepay_api_key="a" * 40,
                abacatepay_webhook_secret=self.secret,
                skip_payment_for_testing=True,
            )
        )
        digest = hmac.new(
            ABACATEPAY_PUBLIC_KEY.encode("utf-8"),
            self.body,
            hashlib.sha256,
        ).digest()
        self.signature = base64.b64encode(digest).decode("ascii")

    def test_valid_webhook_is_accepted_even_in_testing_mode(self) -> None:
        self.pay.require_authenticated_webhook(
            self.body,
            self.secret,
            self.signature,
        )

    def test_missing_secret_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.pay.require_authenticated_webhook(
                self.body,
                None,
                self.signature,
            )
        self.assertEqual(raised.exception.status_code, 401)

    def test_missing_signature_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.pay.require_authenticated_webhook(
                self.body,
                self.secret,
                "",
            )
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
