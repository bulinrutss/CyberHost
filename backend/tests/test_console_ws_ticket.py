import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.console_ticket import ConsoleWsTicket
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.services.console_tickets import (
    authenticate_console_websocket,
    issue_console_ws_ticket,
    redeem_console_ws_ticket,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(secret_key="console-ticket-secret-key-for-tests", console_ws_ticket_seconds=60)


class ConsoleWsTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[User.__table__, ConsoleWsTicket.__table__])
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11999990000",
            name="Ticket User",
            hashed_password="x",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.settings_patch = patch(
            "app.services.console_tickets.get_settings",
            return_value=_settings(),
        )
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_issue_and_redeem_once(self) -> None:
        raw, ttl = issue_console_ws_ticket(self.db, self.user, 7)
        self.assertEqual(ttl, 60)
        self.assertGreaterEqual(len(raw), 32)
        user = redeem_console_ws_ticket(self.db, raw, 7)
        self.assertEqual(user.id, self.user.id)
        with self.assertRaises(HTTPException) as raised:
            redeem_console_ws_ticket(self.db, raw, 7)
        self.assertEqual(raised.exception.status_code, 401)

    def test_wrong_instance_is_rejected(self) -> None:
        raw, _ttl = issue_console_ws_ticket(self.db, self.user, 7)
        with self.assertRaises(HTTPException) as raised:
            redeem_console_ws_ticket(self.db, raw, 8)
        self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(HTTPException) as reused:
            redeem_console_ws_ticket(self.db, raw, 7)
        self.assertEqual(reused.exception.status_code, 401)

    def test_expired_ticket_is_rejected(self) -> None:
        raw, _ttl = issue_console_ws_ticket(self.db, self.user, 7)
        row = self.db.query(ConsoleWsTicket).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            redeem_console_ws_ticket(self.db, raw, 7)
        self.assertEqual(raised.exception.status_code, 401)

    def test_jwt_query_is_rejected(self) -> None:
        raw, _ttl = issue_console_ws_ticket(self.db, self.user, 7)
        with self.assertRaises(HTTPException) as raised:
            authenticate_console_websocket(
                self.db,
                instance_id=7,
                ticket=raw,
                jwt_query="eyJhbGciOiJIUzI1NiJ9.e30.sig",
            )
        self.assertEqual(raised.exception.status_code, 401)
        user = authenticate_console_websocket(
            self.db, instance_id=7, ticket=raw, jwt_query=None
        )
        self.assertEqual(user.id, self.user.id)

    def test_missing_ticket_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            authenticate_console_websocket(
                self.db, instance_id=7, ticket=None, jwt_query=None
            )
        self.assertEqual(raised.exception.status_code, 401)

    def test_unknown_ticket_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            redeem_console_ws_ticket(self.db, "not-a-real-ticket-value-aaaaaaaa", 7)
        self.assertEqual(raised.exception.status_code, 401)

    def test_host_shell_ticket_requires_admin(self) -> None:
        from app.services.console_tickets import issue_host_shell_ticket, redeem_host_shell_ticket

        with self.assertRaises(HTTPException) as raised:
            issue_host_shell_ticket(self.db, self.user)
        self.assertEqual(raised.exception.status_code, 403)
        self.user.is_admin = True
        self.db.commit()
        raw, ttl = issue_host_shell_ticket(self.db, self.user)
        self.assertGreaterEqual(ttl, 15)
        admin = redeem_host_shell_ticket(self.db, raw)
        self.assertEqual(admin.id, self.user.id)
        with self.assertRaises(HTTPException):
            redeem_host_shell_ticket(self.db, raw)

    def test_host_shell_rejects_jwt_query(self) -> None:
        from app.services.console_tickets import (
            authenticate_host_shell_websocket,
            issue_host_shell_ticket,
        )

        self.user.is_admin = True
        self.db.commit()
        raw, _ttl = issue_host_shell_ticket(self.db, self.user)
        with self.assertRaises(HTTPException) as raised:
            authenticate_host_shell_websocket(
                self.db, ticket=raw, jwt_query="eyJhbGciOiJIUzI1NiJ9.e30.sig"
            )
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
