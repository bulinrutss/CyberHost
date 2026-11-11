import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder, CloudStorageOrderStatus
from app.models.coupon import CouponRedemption, DiscountCoupon  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import OrderStatus, VpsInstance, VpsOrder  # noqa: F401
from app.services.billing import extend_paid_until
from app.services.cloud_storage import cancel_pending_order, mark_paid
from app.services.hostname import ACTIVE_ORDER_STATUSES


class CloudStorageMarkPaidTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, CloudStorageOrder.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11988880000",
            name="Cloud User",
            hashed_password="x",
            is_active=True,
            cloud_contracted_gb=0,
            cloud_monthly_cents=0,
            cloud_extra_quota_bytes=0,
            cloud_paid_until=datetime(2026, 9, 25, 23, 59, 59),
            cloud_billing_day=25,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _order(self, **overrides) -> CloudStorageOrder:
        values = {
            "user_id": self.user.id,
            "extra_gb": 50,
            "renewal_months": None,
            "total_cents": 990,
            "status": CloudStorageOrderStatus.PENDING_PAYMENT,
        }
        values.update(overrides)
        order = CloudStorageOrder(**values)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def test_credit_is_applied_once(self) -> None:
        order = self._order(extra_gb=50)
        self.assertTrue(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.db.refresh(order)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)
        self.assertEqual(self.user.cloud_contracted_gb, 50)
        monthly = self.user.cloud_monthly_cents

        self.assertFalse(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.cloud_contracted_gb, 50)
        self.assertEqual(self.user.cloud_monthly_cents, monthly)

    def test_two_orders_accumulate_gb(self) -> None:
        first = self._order(extra_gb=50)
        second = self._order(extra_gb=50)
        self.assertTrue(mark_paid(self.db, first.id))
        self.assertTrue(mark_paid(self.db, second.id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.cloud_contracted_gb, 100)

    def test_renewal_extends_paid_until_once(self) -> None:
        start = datetime(2026, 9, 25, 23, 59, 59)
        self.user.cloud_paid_until = start
        self.user.cloud_billing_day = 25
        self.user.cloud_contracted_gb = 50
        self.user.cloud_monthly_cents = 990
        self.db.commit()

        order = self._order(extra_gb=0, renewal_months=2, total_cents=1980)
        expected = extend_paid_until(start, 2, 25)
        self.assertTrue(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.cloud_paid_until, expected)
        self.assertFalse(self.user.cloud_suspended_for_billing)

        self.assertFalse(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.cloud_paid_until, expected)

    def test_cancelled_order_is_reconciled_once(self) -> None:
        order = self._order(extra_gb=50)
        cancel_pending_order(self.db, self.user, order.id)
        self.db.refresh(order)
        self.assertEqual(order.status, CloudStorageOrderStatus.CANCELLED)
        self.assertIsNotNone(self.db.get(CloudStorageOrder, order.id))

        self.assertTrue(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.db.refresh(order)
        self.assertEqual(order.status, CloudStorageOrderStatus.PAID)
        self.assertEqual(self.user.cloud_contracted_gb, 50)

        self.assertFalse(mark_paid(self.db, order.id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.cloud_contracted_gb, 50)

    def test_paid_order_cannot_be_cancelled(self) -> None:
        order = self._order(extra_gb=50)
        self.assertTrue(mark_paid(self.db, order.id))
        with self.assertRaises(HTTPException) as raised:
            cancel_pending_order(self.db, self.user, order.id)
        self.assertEqual(raised.exception.status_code, 400)

    def test_cancelled_hostname_is_reusable(self) -> None:
        self.assertNotIn(OrderStatus.CANCELLED, ACTIVE_ORDER_STATUSES)

    def test_missing_order_returns_false(self) -> None:
        self.assertFalse(mark_paid(self.db, 99999))


if __name__ == "__main__":
    unittest.main()
