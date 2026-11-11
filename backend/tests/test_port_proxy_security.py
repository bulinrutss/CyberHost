import hashlib
import ssl
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.config import Settings
from app.services.port_proxy import (
    _assert_proxy_pin,
    _fetch_page_catalog,
    _proxy_auth_headers,
    build_port_proxy_ssl_context,
    normalize_port_proxy_pin,
    parse_page_names,
    parse_proxies_payload,
    rename_proxy_page,
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
        "esxi_ssl_pin_sha256": "a" * 64,
        "frontend_url": "https://ruts.dev",
        "api_public_url": "https://ruts.dev",
        "cors_origins": "https://ruts.dev",
        "port_proxy_api_url": "",
        "port_proxy_api_token": "",
        "port_proxy_tls_pin_sha256": "",
        "port_proxy_tls_ca_file": "",
        "port_proxy_tls_insecure": False,
    }
    values.update(overrides)
    return Settings(**values)


def _production(**overrides) -> dict:
    values = {
        "app_environment": "production",
        "abacatepay_enabled": True,
        "abacatepay_api_key": "a" * 40,
        "port_proxy_api_url": "https://127.0.0.1:5443",
        "port_proxy_api_token": "t" * 32,
        "port_proxy_tls_pin_sha256": "b" * 64,
    }
    values.update(overrides)
    return values


class DummyPeer:
    def __init__(self, der: bytes | None) -> None:
        self._der = der

    def getpeercert(self, binary_form: bool = False):
        return self._der if binary_form else {}


class PortProxySettingsTests(unittest.TestCase):
    def test_production_rejects_http_url(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(port_proxy_api_url="http://192.168.0.127:5000"))

    def test_production_rejects_short_token(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(port_proxy_api_token="short"))

    def test_production_rejects_missing_pin(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(port_proxy_tls_pin_sha256=""))

    def test_production_rejects_insecure_tls(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(port_proxy_tls_insecure=True))

    def test_production_accepts_https_token_and_pin(self) -> None:
        settings = _settings(**_production())
        self.assertTrue(settings.port_proxy_api_url.startswith("https://"))
        self.assertEqual(len(settings.port_proxy_api_token), 32)

    def test_empty_url_skips_production_proxy_rules(self) -> None:
        settings = _settings(**_production(port_proxy_api_url="", port_proxy_api_token=""))
        self.assertEqual(settings.port_proxy_api_url, "")


class PortProxyTlsTests(unittest.TestCase):
    def test_pin_is_normalized(self) -> None:
        self.assertEqual(normalize_port_proxy_pin("AA:BB"), "aabb")

    def test_matching_pin_is_accepted(self) -> None:
        der = b"proxy-cert"
        pin = hashlib.sha256(der).hexdigest()
        _assert_proxy_pin(DummyPeer(der), pin)  # type: ignore[arg-type]

    def test_mismatched_pin_is_rejected(self) -> None:
        with self.assertRaises(ssl.SSLError):
            _assert_proxy_pin(DummyPeer(b"proxy-cert"), "a" * 64)  # type: ignore[arg-type]

    def test_https_without_pin_or_ca_fails_closed(self) -> None:
        with self.assertRaises(ssl.SSLError):
            build_port_proxy_ssl_context(
                _settings(port_proxy_api_url="https://127.0.0.1:5443")
            )


class PortProxySchemaTests(unittest.TestCase):
    def test_page_names_must_be_string_map(self) -> None:
        self.assertEqual(parse_page_names({"1": "máquina vazia"}), {"1": "máquina vazia"})
        with self.assertRaises(ValueError):
            parse_page_names(["1"])
        with self.assertRaises(ValueError):
            parse_page_names({"1": 2})

    def test_proxies_payload_rejects_non_object(self) -> None:
        with self.assertRaises(ValueError):
            parse_proxies_payload([{"pass": "1.2.3.4:3389"}])

    def test_proxies_payload_accepts_valid_page(self) -> None:
        proxies, pages = parse_proxies_payload(
            {
                "proxies": [
                    {"listenPort": 10000, "pass": "192.168.0.200:3389"},
                    {"listenPort": 10001},
                ],
                "total_pages": 2,
            }
        )
        self.assertEqual(pages, 2)
        self.assertEqual(len(proxies), 1)


class PortProxyClientTests(unittest.TestCase):
    def setUp(self) -> None:
        import app.services.port_proxy as port_proxy

        port_proxy._pages_cache = None
        port_proxy._cache_proxies = None
        port_proxy._mappings_by_ip_cache = None
        port_proxy._pages_cache_at = 0.0
        port_proxy._cache_at = 0.0

    def test_auth_header_uses_bearer(self) -> None:
        headers = _proxy_auth_headers(_settings(port_proxy_api_token="k" * 32))
        self.assertEqual(headers["Authorization"], "Bearer " + ("k" * 32))

    def test_catalog_sends_bearer_and_parses_schema(self) -> None:
        settings = _settings(
            port_proxy_api_url="https://127.0.0.1:5443",
            port_proxy_api_token="k" * 32,
            port_proxy_tls_insecure=True,
        )
        calls: list[str] = []

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload
                self.status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return self._payload

        class FakeClient:
            def get(self, url, params=None):
                calls.append(url)
                if url.endswith("/get-page-names"):
                    return FakeResp({"1": "máquina vazia"})
                if url.endswith("/check-machines-status"):
                    return FakeResp({"1": True})
                return FakeResp(
                    {
                        "proxies": [{"listenPort": 10000, "pass": "192.168.0.200:3389"}],
                        "total_pages": 1,
                    }
                )

        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = FakeClient()
        fake_cm.__exit__.return_value = False
        with patch("app.services.port_proxy._proxy_http_client", return_value=fake_cm):
            slots = _fetch_page_catalog(settings)
        self.assertTrue(any(url.endswith("/get-page-names") for url in calls))
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].internal_ip, "192.168.0.200")

    def test_catalog_rejects_spoofed_non_object(self) -> None:
        settings = _settings(
            port_proxy_api_url="https://127.0.0.1:5443",
            port_proxy_api_token="k" * 32,
            port_proxy_tls_insecure=True,
        )

        class FakeResp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return ["spoofed"]

        class FakeClient:
            def get(self, url, params=None):
                return FakeResp()

        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = FakeClient()
        fake_cm.__exit__.return_value = False
        with patch("app.services.port_proxy._proxy_http_client", return_value=fake_cm):
            slots = _fetch_page_catalog(settings)
        self.assertEqual(slots, [])

    def test_rename_sends_json_over_authenticated_client(self) -> None:
        settings = _settings(
            port_proxy_api_url="https://127.0.0.1:5443",
            port_proxy_api_token="k" * 32,
            port_proxy_tls_insecure=True,
        )
        posted: dict = {}

        class FakeResp:
            def raise_for_status(self) -> None:
                return None

        class FakeClient:
            def post(self, url, json=None):
                posted["url"] = url
                posted["json"] = json
                return FakeResp()

        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = FakeClient()
        fake_cm.__exit__.return_value = False
        with patch("app.services.port_proxy._proxy_http_client", return_value=fake_cm):
            rename_proxy_page(3, "vps-demo", settings=settings)
        self.assertTrue(posted["url"].endswith("/save-page-name"))
        self.assertEqual(posted["json"], {"page": 3, "name": "vps-demo"})
