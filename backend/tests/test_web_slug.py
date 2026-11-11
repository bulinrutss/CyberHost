import unittest

from fastapi import HTTPException

from app.services.web_slug import (
    normalize_slug,
    path_prefix,
    platform_subdomain_for_site,
    resolved_public_base,
)
from types import SimpleNamespace


class WebSlugTests(unittest.TestCase):
    def test_normalize_slug(self) -> None:
        self.assertEqual(normalize_slug("Minha Loja"), "minha-loja")
        self.assertEqual(normalize_slug("loja_01"), "loja-01")

    def test_rejects_reserved_and_short(self) -> None:
        for raw in ("a", "api", "cyberhost", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(HTTPException):
                    normalize_slug(raw)

    def test_path_prefix(self) -> None:
        self.assertEqual(path_prefix("minha-loja"), "/s/minha-loja")

    def test_resolved_public_base_prefers_env(self) -> None:
        settings = SimpleNamespace(
            web_public_base_url="https://ruts.dev",
            vps_public_ip="147.15.80.246",
            resolved_frontend_url="https://ruts.dev/cyberhost",
        )
        self.assertEqual(resolved_public_base(settings), "https://ruts.dev")

    def test_resolved_public_base_prefers_frontend_over_ip(self) -> None:
        settings = SimpleNamespace(
            web_public_base_url="",
            vps_public_ip="147.15.80.246",
            resolved_frontend_url="https://ruts.dev/cyberhost",
        )
        self.assertEqual(resolved_public_base(settings), "https://ruts.dev")

    def test_platform_subdomain_for_site(self) -> None:
        settings = SimpleNamespace(
            web_public_base_url="https://ruts.dev",
            web_platform_subdomains_enabled=True,
            web_platform_base_domain="",
            resolved_frontend_url="https://ruts.dev/cyberhost",
            vps_public_ip="",
        )
        site = SimpleNamespace(site_slug="minha-loja", domain=None)
        self.assertEqual(platform_subdomain_for_site(site, settings), "minha-loja.ruts.dev")

    def test_platform_subdomain_skipped_with_custom_domain(self) -> None:
        settings = SimpleNamespace(
            web_public_base_url="https://ruts.dev",
            web_platform_subdomains_enabled=True,
            web_platform_base_domain="ruts.dev",
            resolved_frontend_url="https://ruts.dev/cyberhost",
            vps_public_ip="",
        )
        site = SimpleNamespace(site_slug="loja", domain="loja.cliente.com")
        self.assertIsNone(platform_subdomain_for_site(site, settings))


if __name__ == "__main__":
    unittest.main()
