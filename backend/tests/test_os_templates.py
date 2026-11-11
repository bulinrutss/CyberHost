import unittest

from pydantic import ValidationError

from app.schemas.vps import OrderCreate, PriceQuoteRequest
from app.services.os_templates import (
    get_os_template,
    guest_username_for_os,
    list_os_templates,
    os_label_for_slug,
)


class OsTemplateCatalogTests(unittest.TestCase):
    def test_list_excludes_windows_2012(self) -> None:
        slugs = [item.slug for item in list_os_templates()]
        self.assertEqual(slugs, ["sv2016", "sv2019"])
        self.assertEqual(
            [item.template_name for item in list_os_templates()],
            ["VPS-BASE-SV2016", "VPS-BASE-SV2019"],
        )

    def test_sv2012_cannot_be_selected(self) -> None:
        with self.assertRaises(ValueError):
            get_os_template("sv2012")

    def test_legacy_label_for_existing_instances(self) -> None:
        self.assertEqual(os_label_for_slug("sv2012"), "Windows Server 2012")
        self.assertEqual(os_label_for_slug("sv2019"), "Windows Server 2019")

    def test_guest_username_by_os(self) -> None:
        self.assertEqual(guest_username_for_os("sv2016"), "Administrator")
        self.assertEqual(guest_username_for_os("sv2019"), "Administrador")
        self.assertEqual(guest_username_for_os("sv2012"), "Administrador")
        self.assertEqual(get_os_template("sv2019").guest_username, "Administrador")

    def test_order_and_quote_reject_sv2012(self) -> None:
        with self.assertRaises(ValidationError):
            PriceQuoteRequest(plan_id=1, vcpu=2, ram_mb=2048, disk_gb=40, os_template="sv2012")
        with self.assertRaises(ValidationError):
            OrderCreate(hostname="vps-teste", os_template="sv2012")

    def test_hostname_rejects_portuguese_characters(self) -> None:
        from app.services.hostname import HOSTNAME_INVALID_MESSAGE, validate_hostname

        with self.assertRaises(ValueError) as raised:
            validate_hostname("joão-servidor")
        self.assertEqual(str(raised.exception), HOSTNAME_INVALID_MESSAGE)
        with self.assertRaises(ValidationError) as order_error:
            OrderCreate(
                plan_id=1,
                vcpu=2,
                ram_mb=2048,
                disk_gb=40,
                hostname="servidor-são-paulo",
                os_template="sv2016",
            )
        self.assertIn("letras sem acento", str(order_error.exception))
        self.assertNotIn("should match pattern", str(order_error.exception).lower())
        self.assertEqual(validate_hostname("Meu-Servidor"), "meu-servidor")


if __name__ == "__main__":
    unittest.main()
