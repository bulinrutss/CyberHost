import unittest
from datetime import datetime

from app.services.billing import prorate_monthly_delta


class ProrateUntilRenewalTests(unittest.TestCase):
    def test_one_month_left_is_full_delta(self) -> None:
        now = datetime(2026, 8, 27, 12, 0, 0)
        paid = datetime(2026, 9, 27, 23, 59, 59)
        result = prorate_monthly_delta(1000, paid, now=now)
        self.assertEqual(result["amount_cents"], 1000)
        self.assertEqual(result["days_remaining"], 31)
        self.assertFalse(result["prorated"])

    def test_six_months_left_charges_six_cycles(self) -> None:
        now = datetime(2026, 8, 27, 12, 0, 0)
        paid = datetime(2027, 2, 27, 23, 59, 59)
        result = prorate_monthly_delta(1000, paid, now=now)
        self.assertEqual(result["amount_cents"], 6000)
        self.assertEqual(result["monthly_delta_cents"], 1000)
        self.assertGreater(result["days_remaining"], 150)
        self.assertTrue(result["prorated"])

    def test_partial_current_month_only(self) -> None:
        now = datetime(2026, 8, 20, 12, 0, 0)
        paid = datetime(2026, 8, 27, 23, 59, 59)
        result = prorate_monthly_delta(3100, paid, now=now)
        self.assertEqual(result["amount_cents"], 700)
        self.assertEqual(result["days_remaining"], 7)
        self.assertTrue(result["prorated"])

    def test_partial_plus_full_months(self) -> None:
        now = datetime(2026, 8, 20, 12, 0, 0)
        paid = datetime(2026, 10, 27, 23, 59, 59)
        result = prorate_monthly_delta(3100, paid, now=now)
        # 7/31 of Aug cycle + Sep 20–27 wait:
        # Aug 20 -> Aug 27: 7/31 * 3100 = 700
        # Aug 27 -> Sep 27: full 3100
        # Sep 27 -> Oct 27: full 3100
        self.assertEqual(result["amount_cents"], 700 + 3100 + 3100)
        self.assertEqual(result["days_remaining"], (paid.date() - now.date()).days)

    def test_expired_charges_one_month(self) -> None:
        now = datetime(2026, 8, 27, 12, 0, 0)
        paid = datetime(2026, 8, 20, 23, 59, 59)
        result = prorate_monthly_delta(1000, paid, now=now)
        self.assertEqual(result["amount_cents"], 1000)
        self.assertFalse(result["prorated"])

    def test_missing_paid_until_is_full_month(self) -> None:
        result = prorate_monthly_delta(1000, None)
        self.assertEqual(result["amount_cents"], 1000)
        self.assertFalse(result["prorated"])


if __name__ == "__main__":
    unittest.main()
