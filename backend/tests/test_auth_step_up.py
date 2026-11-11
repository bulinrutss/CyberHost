import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, hash_password
from app.database import Base, get_db
from app.models.auth_security import AuthStepUpTicket
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.models.vps_connection import VpsConnectionDomain  # noqa: F401
from app.models.web_site import WebOrder, WebSite  # noqa: F401
from app.services import auth_step_up


def _settings(**overrides) -> SimpleNamespace:
    values = {"secret_key": "k" * 40}
    values.update(overrides)
    return SimpleNamespace(**values)


class AuthStepUpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, AuthStepUpTicket.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11970009999",
            email="stepup@example.com",
            name="Step Up",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
            mfa_enabled=False,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self._settings_patch = patch(
            "app.services.auth_step_up.get_settings",
            return_value=_settings(),
        )
        self._settings_patch.start()

    def tearDown(self) -> None:
        self._settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_issue_rejects_wrong_password(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            auth_step_up.issue_step_up(self.db, self.user, "wrong-password")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_issue_and_verify_token(self) -> None:
        raw, ttl = auth_step_up.issue_step_up(self.db, self.user, "correct-horse")
        self.assertEqual(ttl, auth_step_up.STEP_UP_TTL_SECONDS)
        self.assertTrue(raw)
        self.assertTrue(auth_step_up.verify_step_up(self.db, self.user.id, raw))
        # reusable until expiry
        self.assertTrue(auth_step_up.verify_step_up(self.db, self.user.id, raw))
        self.assertFalse(auth_step_up.verify_step_up(self.db, self.user.id, "bogus"))
        self.assertFalse(auth_step_up.verify_step_up(self.db, self.user.id + 1, raw))

    def test_require_step_up_dependency(self) -> None:
        app = FastAPI()

        @app.get("/secure-dep")
        def secure_dep(user: User = Depends(auth_step_up.require_step_up)):
            return {"ok": True, "user_id": user.id}

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.user

        client = TestClient(app)
        denied = client.get("/secure-dep")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.headers.get("x-step-up-required"), "1")
        self.assertEqual(denied.json()["detail"]["code"], "step_up_required")
        self.assertFalse(denied.json()["detail"]["mfa_enabled"])

        raw, _ttl = auth_step_up.issue_step_up(self.db, self.user, "correct-horse")
        allowed = client.get("/secure-dep", headers={"X-Step-Up-Token": raw})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["user_id"], self.user.id)


if __name__ == "__main__":
    unittest.main()
