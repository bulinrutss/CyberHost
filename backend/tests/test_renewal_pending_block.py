import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsPlan, VpsStatus
from app.services.billing import extend_paid_until
from app.services.vps_renewal import apply_renewal_order, resolve_renewal_order_block


class RenewalBlockHealTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, VpsPlan.__table__, VpsOrder.__table__, VpsInstance.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11970009999",
            email="renova@example.com",
            name="Cliente",
            hashed_password="x",
            is_active=True,
        )
        self.plan = VpsPlan(name="VPS", slug="vps")
        self.db.add_all([self.user, self.plan])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.plan)
        paid = datetime(2026, 9, 27, 23, 59, 59)
        self.instance = VpsInstance(
            user_id=self.user.id,
            order_id=None,
            vm_name="vps-renova",
            vcpu=2,
            ram_mb=2048,
            disk_gb=40,
            status=VpsStatus.RUNNING,
            esxi_host="esxi.local",
            paid_until=paid,
            billing_day=27,
        )
        # order_id is required unique FK — create a dummy original order first
        original = VpsOrder(
            user_id=self.user.id,
            plan_id=self.plan.id,
            vcpu=2,
            ram_mb=2048,
            disk_gb=40,
            hostname="vps-renova",
            status=OrderStatus.ACTIVE,
            total_cents=1000,
        )
        self.db.add(original)
        self.db.commit()
        self.db.refresh(original)
        self.instance.order_id = original.id
        self.db.add(self.instance)
        self.db.commit()
        self.db.refresh(self.instance)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _renewal(self, status: OrderStatus, step: str = "payment_confirmed") -> VpsOrder:
        order = VpsOrder(
            user_id=self.user.id,
            plan_id=self.plan.id,
            vcpu=2,
            ram_mb=2048,
            disk_gb=40,
            hostname=f"renew-{self.instance.id}",
            order_type=OrderType.RENEWAL,
            target_instance_id=self.instance.id,
            renewal_months=12,
            status=status,
            total_cents=5000,
            provision_step=step,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def test_unpaid_checkout_is_cancelled_to_allow_new(self) -> None:
        pending = self._renewal(OrderStatus.PENDING_PAYMENT, "payment_pending")
        self.assertIsNone(resolve_renewal_order_block(self.db, self.instance.id))
        self.db.refresh(pending)
        self.assertEqual(pending.status, OrderStatus.CANCELLED)

    def test_paid_stuck_order_is_applied_then_released(self) -> None:
        before = self.instance.paid_until
        paid = self._renewal(OrderStatus.PAID)
        self.assertIsNone(resolve_renewal_order_block(self.db, self.instance.id))
        self.db.refresh(paid)
        self.db.refresh(self.instance)
        self.assertEqual(paid.status, OrderStatus.ACTIVE)
        self.assertEqual(
            self.instance.paid_until,
            extend_paid_until(before, 12, self.instance.billing_day),
        )

    def test_apply_twice_does_not_double_extend(self) -> None:
        paid = self._renewal(OrderStatus.PAID)
        first = apply_renewal_order(self.db, paid)
        until = first.paid_until
        second = apply_renewal_order(self.db, paid)
        self.assertEqual(second.paid_until, until)
        self.db.refresh(paid)
        self.assertEqual(paid.status, OrderStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
