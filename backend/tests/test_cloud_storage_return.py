import unittest
from pathlib import Path

from app.services.cloud_return import browser_files_url


class CloudStorageReturnTests(unittest.TestCase):
    def test_browser_url_is_generic(self) -> None:
        url = browser_files_url()
        self.assertTrue(url.endswith("/dashboard/files"))
        self.assertNotIn("?", url)
        self.assertNotIn("order=", url)
        self.assertNotIn("gb=", url)
        self.assertNotIn("storage=", url)

    def test_complete_handler_does_not_credit(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "app" / "api" / "payments.py").read_text(
            encoding="utf-8"
        )
        start = src.index("def cloud_storage_payment_complete")
        end = src.index("@router.post(\"/webhook/abacatepay\")")
        body = src[start:end]
        self.assertNotIn("mark_cloud_storage_paid", body)
        self.assertNotIn("get_db", body)
        self.assertNotIn("order_is_paid_at_provider", body)
        self.assertIn("browser_files_url", body)


if __name__ == "__main__":
    unittest.main()
