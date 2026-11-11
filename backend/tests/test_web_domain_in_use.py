import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder  # noqa: F401
from app.models.user import User
from app.models.vps import VpsOrder  # noqa: F401
from app.models.web_site import WebOrder, WebOrderStatus, WebSite, WebSiteStatus
from app.services.web_domain import domain_in_use


class WebDomainInUseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, WebOrder.__table__, WebSite.__table__],
        )
        self.db = sessionmaker(bind=self.engine)()
        user = User(
            phone="11990001111",
            email="dom@example.com",
            name="Test",
            hashed_password="x",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.user_id = user.id

    def test_deleted_site_does_not_reserve_domain(self) -> None:
        site = WebSite(
            user_id=self.user_id,
            site_slug="old",
            domain="loja.exemplo.com.br",
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            port=30001,
            data_path="/tmp/old",
            status=WebSiteStatus.DELETED,
        )
        self.db.add(site)
        self.db.commit()
        self.assertFalse(domain_in_use(self.db, "loja.exemplo.com.br"))

    def test_active_order_with_deleted_site_does_not_reserve_domain(self) -> None:
        order = WebOrder(
            user_id=self.user_id,
            site_slug="old",
            domain="festa.exemplo.com.br",
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            total_cents=1000,
            status=WebOrderStatus.ACTIVE,
        )
        self.db.add(order)
        self.db.flush()
        site = WebSite(
            user_id=self.user_id,
            order_id=order.id,
            site_slug="old",
            domain=None,
            ram_mb=512,
            disk_mb=1024,
            cpu_percent=50,
            port=30002,
            data_path="/tmp/old",
            status=WebSiteStatus.DELETED,
        )
        self.db.add(site)
        self.db.commit()
        self.assertFalse(domain_in_use(self.db, "festa.exemplo.com.br"))


if __name__ == "__main__":
    unittest.main()
