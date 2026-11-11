import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import OrderStatus, OrderType, VpsInstance, VpsOrder, VpsPlan  # noqa: F401
from app.schemas.auth import AdminUserCreate
from app.services.admin_management import create_courtesy_vps_order, create_panel_user
from fastapi import HTTPException


class AdminUserCreateSchemaTests(unittest.TestCase):
    def test_requires_email(self) -> None:
        with self.assertRaises(ValidationError):
            AdminUserCreate(
                phone="11970001111",
                name="Cliente Novo",
                password="correct-horse",
            )


class CreatePanelUserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[User.__table__])
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_creates_with_email(self) -> None:
        user = create_panel_user(
            self.db,
            phone="11970001111",
            email="Cliente@Example.com",
            name="Maria Cliente",
            password="correct-horse",
        )
        self.assertEqual(user.email, "cliente@example.com")
        self.assertFalse(user.is_admin)

    def test_rejects_duplicate_email(self) -> None:
        create_panel_user(
            self.db,
            phone="11970001111",
            email="maria@example.com",
            name="Maria",
            password="correct-horse",
        )
        with self.assertRaises(HTTPException) as raised:
            create_panel_user(
                self.db,
                phone="11970002222",
                email="maria@example.com",
                name="Outra",
                password="correct-horse",
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("E-mail", raised.exception.detail)


class CreateCourtesyVpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, VpsPlan.__table__, VpsOrder.__table__, VpsInstance.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11970003333",
            email="cliente@example.com",
            name="Cliente",
            hashed_password="x",
            is_active=True,
            is_admin=False,
        )
        self.plan = VpsPlan(
            slug="vps",
            name="VPS",
            min_vcpu=1,
            max_vcpu=8,
            min_ram_mb=1024,
            max_ram_mb=8192,
            default_disk_gb=30,
            max_disk_gb=500,
            is_active=True,
        )
        self.db.add_all([self.user, self.plan])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.plan)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_creates_paid_admin_order(self) -> None:
        order = create_courtesy_vps_order(
            self.db,
            user_id=self.user.id,
            hostname="cliente-web",
            os_template="sv2016",
            plan_id=self.plan.id,
            vcpu=2,
            ram_mb=4096,
            disk_gb=40,
        )
        self.db.commit()
        self.assertEqual(order.user_id, self.user.id)
        self.assertEqual(order.hostname, "cliente-web")
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.order_type, OrderType.ADMIN)
        self.assertEqual(order.total_cents, 0)
        self.assertEqual(order.os_template, "sv2016")

    def test_requires_active_account(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            create_courtesy_vps_order(
                self.db,
                user_id=9999,
                hostname="sem-conta",
            )
        self.assertEqual(raised.exception.status_code, 400)
