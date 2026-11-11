import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services import web_nginx


def _settings(root: str, **overrides) -> SimpleNamespace:
    values = {
        "web_nginx_snippet_dir": root,
        "web_sites_data_path": root,
        "web_port_range_start": 30000,
        "web_port_range_end": 30499,
        "web_nginx_reload": False,
        "web_ssl_enabled": True,
        "web_acme_webroot": "/var/www/acme",
        "web_public_base_url": "https://ruts.dev",
        "web_platform_subdomains_enabled": True,
        "web_platform_base_domain": "ruts.dev",
        "resolved_frontend_url": "https://ruts.dev/cyberhost",
        "vps_public_ip": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class WebNginxTests(unittest.TestCase):
    def test_path_snippet_redirects_to_platform_subdomain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=7, site_slug="minha-loja", domain=None, port=30001)
            settings = _settings(tmp)
            with patch.object(web_nginx, "get_settings", return_value=settings):
                path = web_nginx.write_path_snippet(site, settings)
            body = path.read_text(encoding="utf-8")
            self.assertIn("return 301 https://minha-loja.ruts.dev/;", body)
            self.assertNotIn("proxy_pass", body)

    def test_platform_vhost_when_no_custom_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=9, site_slug="loja", domain=None, port=30003)
            settings = _settings(tmp)
            with patch.object(web_nginx, "get_settings", return_value=settings):
                with patch("app.services.web_ssl.cert_paths", return_value=None):
                    path = web_nginx.write_vhost_snippet(site, settings)
            assert path is not None
            body = path.read_text(encoding="utf-8")
            self.assertIn("server_name loja.ruts.dev;", body)
            self.assertNotIn("www.loja.ruts.dev", body)

    def test_domain_snippet_when_domain_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=8, site_slug="loja", domain="loja.exemplo.com.br", port=30002)
            settings = _settings(tmp)
            with patch.object(web_nginx, "get_settings", return_value=settings):
                with patch("app.services.web_ssl.cert_paths", return_value=None):
                    path = web_nginx.write_vhost_snippet(site, settings)
            assert path is not None
            body = path.read_text(encoding="utf-8")
            self.assertIn("server_name loja.exemplo.com.br www.loja.exemplo.com.br;", body)
            self.assertIn("/.well-known/acme-challenge/", body)
            self.assertNotIn("listen 443", body)

    def test_domain_snippet_with_ssl_cert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=8, site_slug="loja", domain="loja.exemplo.com.br", port=30002)
            settings = _settings(tmp)
            cert = (
                Path("/etc/letsencrypt/live/cyberhost-site-8/fullchain.pem"),
                Path("/etc/letsencrypt/live/cyberhost-site-8/privkey.pem"),
            )
            with patch.object(web_nginx, "get_settings", return_value=settings):
                with patch("app.services.web_ssl.cert_paths", return_value=cert):
                    path = web_nginx.write_vhost_snippet(site, settings)
            body = path.read_text(encoding="utf-8")
            self.assertIn("listen 443 ssl http2;", body)
            self.assertIn("return 301 https://$host$request_uri;", body)
            self.assertIn("fullchain.pem", body)

    def test_vhost_removed_when_platform_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=9, site_slug="loja", domain=None, port=30003)
            settings = _settings(tmp, web_platform_subdomains_enabled=False)
            domain_file = Path(tmp) / "site-9.conf"
            domain_file.write_text("server {}", encoding="utf-8")
            with patch.object(web_nginx, "get_settings", return_value=settings):
                result = web_nginx.write_vhost_snippet(site, settings)
            self.assertIsNone(result)
            self.assertFalse(domain_file.exists())

    def test_rejects_port_outside_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = SimpleNamespace(id=10, site_slug="x", domain="loja.exemplo.com.br", port=80)
            settings = _settings(tmp)
            with self.assertRaises(ValueError):
                web_nginx.write_vhost_snippet(site, settings)


if __name__ == "__main__":
    unittest.main()
