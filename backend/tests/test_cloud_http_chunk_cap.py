import unittest

from app.config import Settings


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


class CloudHttpChunkCapTests(unittest.TestCase):
    def test_default_stays_under_one_megabyte_proxy(self) -> None:
        settings = _settings()
        self.assertEqual(settings.cloud_files_http_chunk_max_bytes, 768 * 1024)
        self.assertLess(settings.cloud_files_chunk_size_bytes, 1024 * 1024)
        self.assertEqual(settings.cloud_files_chunk_size_bytes, 768 * 1024)

    def test_zero_http_cap_uses_discord_limit(self) -> None:
        settings = _settings(
            cloud_files_http_chunk_max_bytes=0,
            discord_attachment_limit_bytes=10 * 1024 * 1024,
        )
        self.assertEqual(settings.cloud_files_chunk_size_bytes, 10 * 1024 * 1024 - 1024)

    def test_http_cap_cannot_exceed_discord(self) -> None:
        settings = _settings(
            cloud_files_http_chunk_max_bytes=50 * 1024 * 1024,
            discord_attachment_limit_bytes=8 * 1024 * 1024,
        )
        self.assertEqual(settings.cloud_files_chunk_size_bytes, 8 * 1024 * 1024 - 1024)
