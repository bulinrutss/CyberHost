"""Domínios personalizados em portas VPS."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.vps import VpsInstance, VpsStatus
from app.models.vps_connection import VpsConnectionDomain
from app.services.port_proxy import PortMapping
from app.services.vps_connection_domains import upsert_connection_domain
from app.services.vps_nginx import supports_http_proxy


class SupportsHttpProxyTests(unittest.TestCase):
    def test_web_ports_supported(self) -> None:
        self.assertTrue(supports_http_proxy(80))
        self.assertTrue(supports_http_proxy(443))
        self.assertFalse(supports_http_proxy(3389))


class UpsertConnectionDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            bind=engine,
            tables=[
                User.__table__,
                VpsInstance.__table__,
                VpsConnectionDomain.__table__,
            ],
        )
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="5511999999999", name="Cliente", password_hash="x")
        self.db.add(self.user)
        self.db.commit()
        self.instance = VpsInstance(
            user_id=self.user.id,
            vm_name="vm-test",
            vcpu=2,
            ram_mb=4096,
            ip_address="192.168.0.210",
            status=VpsStatus.RUNNING,
            esxi_host="192.168.0.125",
        )
        self.db.add(self.instance)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    @patch("app.services.vps_connection_domains.configure_domain")
    @patch("app.services.vps_connection_domains.get_port_mappings_for_ip")
    def test_creates_connection_for_valid_port(
        self,
        mock_mappings,
        mock_configure,
    ) -> None:
        mock_mappings.return_value = [
            PortMapping(
                public_host="203.0.113.10",
                public_port=15001,
                internal_host="192.168.0.210",
                internal_port=80,
                label="HTTP",
            )
        ]
        mock_configure.return_value = False
        conn = upsert_connection_domain(
            self.db,
            self.instance,
            self.user,
            domain_raw="app.exemplo.com",
            public_port=15001,
        )
        self.assertEqual(conn.domain, "app.exemplo.com")
        self.assertEqual(conn.public_port, 15001)
        self.assertEqual(conn.internal_port, 80)
        mock_configure.assert_called_once()

    @patch("app.services.vps_connection_domains.get_port_mappings_for_ip")
    def test_rejects_unknown_public_port(self, mock_mappings) -> None:
        mock_mappings.return_value = []
        with self.assertRaises(HTTPException) as ctx:
            upsert_connection_domain(
                self.db,
                self.instance,
                self.user,
                domain_raw="app.exemplo.com",
                public_port=99999,
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
