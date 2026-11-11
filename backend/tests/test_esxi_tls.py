import hashlib
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings
from app.esxi_tls import (
    assert_esxi_https_url,
    assert_peer_pin,
    build_esxi_ssl_context,
    normalize_esxi_pin,
    read_esxi_https,
)


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_environment": "development",
        "abacatepay_enabled": False,
        "abacatepay_api_key": "",
        "abacatepay_webhook_secret": "w" * 40,
        "skip_payment_for_testing": False,
        "secret_key": "k" * 40,
        "esxi_disable_ssl_verify": False,
        "esxi_ssl_pin_sha256": "a" * 64,
        "esxi_ssl_ca_file": "",
        "frontend_url": "https://ruts.dev",
        "api_public_url": "https://ruts.dev",
        "cors_origins": "https://ruts.dev",
    }
    values.update(overrides)
    return Settings(**values)


class DummyPeer:
    def __init__(self, der: bytes | None) -> None:
        self._der = der

    def getpeercert(self, binary_form: bool = False):
        return self._der if binary_form else {}


class EsxiTlsTests(unittest.TestCase):
    def test_production_rejects_disabled_tls(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(
                app_environment="production",
                esxi_disable_ssl_verify=True,
                abacatepay_enabled=True,
                abacatepay_api_key="a" * 40,
            )

    def test_production_requires_pin_or_ca(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(
                app_environment="production",
                esxi_ssl_pin_sha256="",
                abacatepay_enabled=True,
                abacatepay_api_key="a" * 40,
            )

    def test_pin_is_normalized(self) -> None:
        self.assertEqual(
            normalize_esxi_pin("AA:BB:CC:DD"),
            "aabbccdd",
        )

    def test_matching_pin_is_accepted(self) -> None:
        der = b"esxi-cert"
        pin = hashlib.sha256(der).hexdigest()
        assert_peer_pin(DummyPeer(der), pin)  # type: ignore[arg-type]

    def test_mismatched_pin_is_rejected(self) -> None:
        der = b"esxi-cert"
        with self.assertRaises(ssl.SSLError):
            assert_peer_pin(DummyPeer(der), "a" * 64)  # type: ignore[arg-type]

    def test_missing_peer_cert_is_rejected(self) -> None:
        with self.assertRaises(ssl.SSLError):
            assert_peer_pin(DummyPeer(None), "a" * 64)  # type: ignore[arg-type]

    def test_verified_context_installs_pin_wrapper(self) -> None:
        context = build_esxi_ssl_context(_settings())
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)
        self.assertNotEqual(context.wrap_socket, ssl.SSLContext.wrap_socket)

    def test_disabled_context_skips_pin(self) -> None:
        context = build_esxi_ssl_context(
            _settings(esxi_disable_ssl_verify=True, esxi_ssl_pin_sha256="")
        )
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertIs(context.wrap_socket.__func__, ssl.SSLContext.wrap_socket)  # type: ignore[attr-defined]

    def test_connect_without_trust_anchor_fails_closed(self) -> None:
        with self.assertRaises(ssl.SSLError):
            build_esxi_ssl_context(
                SimpleNamespace(
                    esxi_disable_ssl_verify=False,
                    esxi_ssl_pin_sha256="",
                    esxi_ssl_ca_file="",
                    esxi_host="192.168.0.125",
                )
            )

    def test_guest_transfer_rejects_http_and_foreign_host(self) -> None:
        settings = _settings()
        with self.assertRaises(ValueError):
            assert_esxi_https_url("http://192.168.0.125/guestFile", settings)
        with self.assertRaises(ValueError):
            assert_esxi_https_url("https://evil.example/guestFile", settings)
        with self.assertRaises(ValueError):
            assert_esxi_https_url("https://192.168.0.125:444/guestFile", settings)
        parsed = assert_esxi_https_url(
            "https://192.168.0.125/guestFile?id=1",
            settings,
        )
        self.assertEqual(parsed.hostname, "192.168.0.125")

    def test_guest_transfer_caps_response_size(self) -> None:
        settings = _settings(esxi_disable_ssl_verify=True, esxi_ssl_pin_sha256="")

        class FakeResponse:
            def __init__(self) -> None:
                self._remaining = b"x" * 100

            def read(self, size: int = -1) -> bytes:
                if not self._remaining:
                    return b""
                chunk = self._remaining[:size]
                self._remaining = self._remaining[size:]
                return chunk

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        class FakeOpener:
            def open(self, request: object, timeout: float = 0) -> FakeResponse:
                return FakeResponse()

        with patch("app.esxi_tls.urllib.request.build_opener", return_value=FakeOpener()):
            with self.assertRaises(ValueError) as raised:
                read_esxi_https(
                    "https://192.168.0.125/guestFile",
                    settings,
                    max_bytes=16,
                )
        self.assertIn("limite", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
