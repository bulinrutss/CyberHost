import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.coupon import CouponRedemption, DiscountCoupon
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.models.web_site import WebOrder  # noqa: F401
from app.services.coupons import (
    apply_coupon_to_subtotal,
    redeem_coupon_for_order,
    redeem_coupon_for_web_order,
    release_coupon_reservation,
    release_web_coupon_reservation,
    reserve_coupon_for_order,
)


class CouponReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                DiscountCoupon.__table__,
                VpsOrder.__table__,
                WebOrder.__table__,
                CouponRedemption.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.coupon = DiscountCoupon(
            code="SAVE10",
            description="teste",
            discount_percent=10,
            discount_cents=None,
            max_uses=1,
            used_count=0,
            is_active=True,
        )
        self.db.add(self.coupon)
        self.db.commit()
        self.db.refresh(self.coupon)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_quote_does_not_consume_uses(self) -> None:
        discount, total, coupon = apply_coupon_to_subtotal(self.db, "save10", 1000)
        self.assertEqual(discount, 100)
        self.assertEqual(total, 900)
        self.assertEqual(coupon.id, self.coupon.id)
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 0)

    def test_reserve_respects_max_uses(self) -> None:
        discount, total, coupon = reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        self.assertEqual(discount, 100)
        self.assertEqual(total, 900)
        self.assertEqual(coupon.used_count, 1)

        with self.assertRaises(HTTPException) as raised:
            reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Cupom esgotado")
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)

    def test_release_allows_another_reserve(self) -> None:
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        release_coupon_reservation(self.db, order_id=41, coupon_id=self.coupon.id)
        self.db.commit()
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 0)

        reserve_coupon_for_order(self.db, "SAVE10", 2000)
        self.db.commit()
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)

    def test_redeem_is_idempotent_and_does_not_double_count(self) -> None:
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        redeem_coupon_for_order(self.db, order_id=7, coupon_id=self.coupon.id)
        redeem_coupon_for_order(self.db, order_id=7, coupon_id=self.coupon.id)
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)
        self.assertEqual(self.db.query(CouponRedemption).count(), 1)

    def test_legacy_redeem_respects_max_uses(self) -> None:
        redeem_coupon_for_order(self.db, order_id=11, coupon_id=self.coupon.id)
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)

        redeem_coupon_for_order(self.db, order_id=12, coupon_id=self.coupon.id)
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)
        self.assertEqual(self.db.query(CouponRedemption).count(), 2)

    def test_unlimited_coupon_can_reserve_twice(self) -> None:
        self.coupon.max_uses = None
        self.db.commit()
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 2)

    def test_paid_reservation_is_not_released(self) -> None:
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        redeem_coupon_for_order(self.db, order_id=9, coupon_id=self.coupon.id)
        release_coupon_reservation(self.db, order_id=9, coupon_id=self.coupon.id)
        self.db.commit()
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)

    def test_web_release_allows_another_reserve(self) -> None:
        reserve_coupon_for_order(self.db, "SAVE10", 1000)
        self.db.commit()
        release_web_coupon_reservation(self.db, web_order_id=41, coupon_id=self.coupon.id)
        self.db.commit()
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 0)

        reserve_coupon_for_order(self.db, "SAVE10", 2000)
        self.db.commit()
        redeem_coupon_for_web_order(self.db, web_order_id=42, coupon_id=self.coupon.id)
        self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.used_count, 1)
        self.assertEqual(
            self.db.query(CouponRedemption).filter(CouponRedemption.web_order_id == 42).count(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
