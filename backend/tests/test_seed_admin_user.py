import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password, verify_password
from app.database import Base
from app.services.admin_bootstrap import seed_admin_user
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401


class SeedAdminUserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[User.__table__])
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_creates_admin_when_missing(self) -> None:
        result = seed_admin_user(
            self.db,
            admin_phone="11999999999",
            admin_password="bootstrap-secret",
        )
        self.assertEqual(result, "created")
        user = self.db.query(User).filter(User.phone == "11999999999").one()
        self.assertTrue(user.is_admin)
        self.assertTrue(verify_password("bootstrap-secret", user.hashed_password))

    def test_does_not_reset_existing_password(self) -> None:
        original = hash_password("panel-rotated-secret")
        self.db.add(
            User(
                phone="11999999999",
                name="Administrador",
                hashed_password=original,
                is_admin=True,
                is_active=True,
            )
        )
        self.db.commit()

        result = seed_admin_user(
            self.db,
            admin_phone="11999999999",
            admin_password="leaked-env-password",
        )
        self.assertEqual(result, "exists")
        user = self.db.query(User).filter(User.phone == "11999999999").one()
        self.assertEqual(user.hashed_password, original)
        self.assertTrue(verify_password("panel-rotated-secret", user.hashed_password))
        self.assertFalse(verify_password("leaked-env-password", user.hashed_password))

    def test_does_not_promote_or_reactivate_existing_user(self) -> None:
        original = hash_password("keep-me")
        self.db.add(
            User(
                phone="11988887777",
                name="Cliente",
                hashed_password=original,
                is_admin=False,
                is_active=False,
            )
        )
        self.db.commit()

        result = seed_admin_user(
            self.db,
            admin_phone="11988887777",
            admin_password="should-not-apply",
        )
        self.assertEqual(result, "exists")
        user = self.db.query(User).filter(User.phone == "11988887777").one()
        self.assertFalse(user.is_admin)
        self.assertFalse(user.is_active)
        self.assertEqual(user.hashed_password, original)

    def test_skips_create_without_password(self) -> None:
        result = seed_admin_user(
            self.db,
            admin_phone="11977776666",
            admin_password="",
        )
        self.assertEqual(result, "skipped")
        self.assertIsNone(self.db.query(User).filter(User.phone == "11977776666").first())
