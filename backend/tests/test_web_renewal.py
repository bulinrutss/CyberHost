import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.user import User
from app.models.web_site import WebOrder, WebOrderStatus, WebOrderType, WebSite, WebSiteStatus
from app.services.web_renewal import apply_web_renewal_order, resolve_web_renewal_order_block


class WebRenewalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, WebOrder.__table__, WebSite.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11980001111",
            email="site@example.com",
            name="Cliente",
            hashed_password="x",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        paid = datetime(2026, 9, 27, 23, 59, 59)
        self.site = WebSite(
            user_id=self.user.id,
            order_id=None,
            site_slug="loja",
            domain=None,
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            port=9100,
            data_path="/tmp/site",
            status=WebSiteStatus.STOPPED,
            paid_until=paid,
            billing_day=27,
            suspended_for_billing=True,
        )
        self.db.add(self.site)
        self.db.commit()
        self.db.refresh(self.site)

    def test_apply_renewal_extends_paid_until(self) -> None:
        order = WebOrder(
            user_id=self.user.id,
            order_type=WebOrderType.RENEWAL,
            target_site_id=self.site.id,
            renewal_months=2,
            site_slug=self.site.site_slug,
            ram_mb=self.site.ram_mb,
            disk_mb=self.site.disk_mb,
            cpu_percent=self.site.cpu_percent,
            total_cents=1900,
            status=WebOrderStatus.PAID,
            provision_step="payment_confirmed",
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        apply_web_renewal_order(self.db, order)
        self.db.refresh(self.site)
        self.db.refresh(order)

        self.assertEqual(order.status, WebOrderStatus.ACTIVE)
        self.assertFalse(self.site.suspended_for_billing)
        self.assertEqual(self.site.paid_until.month, 11)

    def test_cancel_stale_pending_renewal(self) -> None:
        order = WebOrder(
            user_id=self.user.id,
            order_type=WebOrderType.RENEWAL,
            target_site_id=self.site.id,
            renewal_months=1,
            site_slug=self.site.site_slug,
            ram_mb=self.site.ram_mb,
            disk_mb=self.site.disk_mb,
            cpu_percent=self.site.cpu_percent,
            total_cents=1000,
            status=WebOrderStatus.PENDING_PAYMENT,
        )
        self.db.add(order)
        self.db.commit()

        blocked = resolve_web_renewal_order_block(self.db, self.site.id)
        self.assertIsNone(blocked)
        self.db.refresh(order)
        self.assertEqual(order.status, WebOrderStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
