import unittest

from pydantic import ValidationError

from app.config import Settings, _is_https_url, _origin_from_url


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
        "frontend_url": "http://localhost:3000",
        "api_public_url": "http://localhost:8810",
        "cors_origins": "http://localhost:3000,http://127.0.0.1:3000",
    }
    values.update(overrides)
    return Settings(**values)


def _production(**overrides) -> dict:
    values = {
        "app_environment": "production",
        "abacatepay_enabled": True,
        "abacatepay_api_key": "a" * 40,
        "frontend_url": "https://ruts.dev",
        "api_public_url": "https://ruts.dev",
        "cors_origins": "https://ruts.dev",
    }
    values.update(overrides)
    return values


class HttpsPublicUrlTests(unittest.TestCase):
    def test_origin_strips_path(self) -> None:
        self.assertEqual(_origin_from_url("https://ruts.dev/cyberhost"), "https://ruts.dev")
        self.assertTrue(_is_https_url("https://ruts.dev"))
        self.assertFalse(_is_https_url("http://ruts.dev"))

    def test_development_allows_http_urls(self) -> None:
        settings = _settings()
        self.assertEqual(settings.resolved_frontend_url, "http://localhost:3000")
        self.assertEqual(settings.resolved_api_public_url, "http://localhost:8810")

    def test_production_accepts_https_urls_and_cors(self) -> None:
        settings = _settings(**_production())
        self.assertEqual(settings.resolved_frontend_url, "https://ruts.dev")
        self.assertIn("https://ruts.dev", settings.cors_origin_list)

    def test_production_rejects_http_frontend_url(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(frontend_url="http://ruts.dev"))

    def test_production_rejects_http_api_url(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(api_public_url="http://ruts.dev"))

    def test_production_rejects_http_public_cors(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(
                **_production(
                    cors_origins="http://ruts.dev,https://ruts.dev",
                )
            )

    def test_production_requires_frontend_origin_in_cors(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(**_production(cors_origins="https://other.example"))


if __name__ == "__main__":
    unittest.main()
