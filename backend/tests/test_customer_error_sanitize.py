import unittest

from app.services.provision_progress import CUSTOMER_GENERIC_ERROR, sanitize_customer_error


class CustomerErrorSanitizeTests(unittest.TestCase):
    def test_replaces_vendor_copy(self) -> None:
        self.assertEqual(
            sanitize_customer_error("VMware Tools não está instalado nesta VM no ESXi"),
            CUSTOMER_GENERIC_ERROR,
        )
        self.assertEqual(
            sanitize_customer_error("Falha ao conectar no ESXi"),
            CUSTOMER_GENERIC_ERROR,
        )

    def test_keeps_unrelated_errors(self) -> None:
        self.assertEqual(sanitize_customer_error("Disco cheio"), "Disco cheio")
        self.assertIsNone(sanitize_customer_error(None))
        self.assertIsNone(sanitize_customer_error(""))


if __name__ == "__main__":
    unittest.main()
