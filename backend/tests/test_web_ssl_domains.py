import unittest

from app.models.web_site import WebSite, WebSiteStatus
from app.services.web_ssl import (
    _site_id_from_cert_name,
    certificate_covers_site,
    required_cert_domains,
)


class WebSslDomainTests(unittest.TestCase):
    def test_cert_name_to_site_id(self) -> None:
        self.assertEqual(_site_id_from_cert_name("cyberhost-site-8"), 8)
        self.assertIsNone(_site_id_from_cert_name("ruts.dev"))

    def test_required_domains_custom_includes_www(self) -> None:
        site = WebSite(
            id=1,
            user_id=1,
            site_slug="loja",
            domain="loja.exemplo.com.br",
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            port=30001,
            data_path="/tmp/x",
            status=WebSiteStatus.RUNNING,
        )
        required = required_cert_domains(site)
        self.assertIn("loja.exemplo.com.br", required)
        self.assertIn("www.loja.exemplo.com.br", required)

    def test_certificate_covers_false_without_files(self) -> None:
        site = WebSite(
            id=99999,
            user_id=1,
            site_slug="x",
            domain="novo.exemplo.com.br",
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            port=30001,
            data_path="/tmp/x",
            status=WebSiteStatus.RUNNING,
        )
        self.assertFalse(certificate_covers_site(site))


if __name__ == "__main__":
    unittest.main()
