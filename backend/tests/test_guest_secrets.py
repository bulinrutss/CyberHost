import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.guest_secrets import (
    SEAL_PREFIX,
    instance_windows_password,
    is_sealed,
    open_windows_password,
    seal_legacy_windows_passwords,
    seal_windows_password,
    set_instance_windows_password,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(secret_key="k" * 40)


class GuestSecretsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patcher = patch("app.services.guest_secrets.get_settings", return_value=_settings())
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_roundtrip_does_not_store_plaintext(self) -> None:
        plain = "Win#Pass-Example"
        sealed = seal_windows_password(plain)
        self.assertIsNotNone(sealed)
        self.assertTrue(is_sealed(sealed))
        self.assertTrue(sealed.startswith(SEAL_PREFIX))
        self.assertNotIn(plain, sealed)
        self.assertEqual(open_windows_password(sealed), plain)

    def test_legacy_plaintext_still_opens(self) -> None:
        self.assertEqual(open_windows_password("legacy-plain"), "legacy-plain")
        self.assertFalse(is_sealed("legacy-plain"))

    def test_seal_is_idempotent(self) -> None:
        sealed = seal_windows_password("once")
        self.assertEqual(seal_windows_password(sealed), sealed)

    def test_invalid_token_returns_none(self) -> None:
        self.assertIsNone(open_windows_password(SEAL_PREFIX + "not-a-fernet-token"))

    def test_empty_is_none(self) -> None:
        self.assertIsNone(seal_windows_password(None))
        self.assertIsNone(seal_windows_password(""))
        self.assertIsNone(open_windows_password(None))

    def test_backfill_seals_plaintext_and_skips_already_sealed(self) -> None:
        plain = SimpleNamespace(windows_admin_password="PlainWin1")
        already = SimpleNamespace(
            windows_admin_password=seal_windows_password("AlreadySealed")
        )
        none = SimpleNamespace(windows_admin_password=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [plain, already, none]
        changed = seal_legacy_windows_passwords(db)
        self.assertEqual(changed, 1)
        db.commit.assert_called_once()
        self.assertTrue(is_sealed(plain.windows_admin_password))
        self.assertNotIn("PlainWin1", plain.windows_admin_password or "")
        self.assertEqual(instance_windows_password(plain), "PlainWin1")
        self.assertEqual(instance_windows_password(already), "AlreadySealed")
        self.assertIsNone(none.windows_admin_password)

    def test_set_helper_stores_sealed_value(self) -> None:
        row = SimpleNamespace(windows_admin_password=None)
        set_instance_windows_password(row, "NewPass#1")
        self.assertTrue(is_sealed(row.windows_admin_password))
        self.assertEqual(instance_windows_password(row), "NewPass#1")
