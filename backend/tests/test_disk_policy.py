import unittest

from app.services.disk_policy import SYSTEM_DISK_OVERHEAD_GB, provisioned_disk_gb


class DiskPolicyTests(unittest.TestCase):
    def test_create_adds_ten_gb_for_system(self) -> None:
        self.assertEqual(SYSTEM_DISK_OVERHEAD_GB, 10)
        self.assertEqual(provisioned_disk_gb(30), 40)
        self.assertEqual(provisioned_disk_gb(40), 50)
        self.assertEqual(provisioned_disk_gb(100), 110)

    def test_does_not_change_contracted_zero_guard(self) -> None:
        self.assertEqual(provisioned_disk_gb(0), 10)


if __name__ == "__main__":
    unittest.main()
