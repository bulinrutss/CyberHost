import unittest
from datetime import datetime

from app.models.vps import VpsStatus
from app.schemas.vps import VpsInstanceAdminDetailResponse


def _admin_detail_payload(**extra):
    payload = {
        "id": 1,
        "vm_name": "vps-teste",
        "vcpu": 2,
        "ram_mb": 2048,
        "ip_address": "192.168.0.50",
        "status": VpsStatus.RUNNING,
        "esxi_host": "esxi.local",
        "error_message": None,
        "created_at": datetime(2026, 1, 1),
        "user_id": 9,
        "user_phone": "11970001111",
        "user_name": "Cliente",
        "power_state": "poweredOn",
        "tools_ok": True,
        "metrics": {
            "cpu_allocated": 2,
            "ram_allocated_mb": 2048,
        },
        "custom_monthly_cents": None,
    }
    payload.update(extra)
    return payload


class AdminVpsRdpSchemaTests(unittest.TestCase):
    def test_admin_detail_keeps_rdp_login_fields(self) -> None:
        parsed = VpsInstanceAdminDetailResponse.model_validate(
            _admin_detail_payload(
                windows_credentials={"username": "Administrator", "password": "example-pass"},
                rdp_connection_address="ruts.dev:33891",
            )
        )
        dumped = parsed.model_dump()
        self.assertEqual(dumped["windows_credentials"]["username"], "Administrator")
        self.assertEqual(dumped["windows_credentials"]["password"], "example-pass")
        self.assertTrue(dumped["windows_credentials"]["has_password"])
        self.assertEqual(dumped["rdp_connection_address"], "ruts.dev:33891")

    def test_admin_detail_allows_missing_rdp(self) -> None:
        parsed = VpsInstanceAdminDetailResponse.model_validate(_admin_detail_payload())
        self.assertIsNone(parsed.windows_credentials)
        self.assertIsNone(parsed.rdp_connection_address)

    def test_admin_detail_allows_password_redacted(self) -> None:
        parsed = VpsInstanceAdminDetailResponse.model_validate(
            _admin_detail_payload(
                windows_credentials={
                    "username": "Administrator",
                    "password": None,
                    "has_password": True,
                },
            )
        )
        self.assertIsNone(parsed.windows_credentials.password)
        self.assertTrue(parsed.windows_credentials.has_password)


if __name__ == "__main__":
    unittest.main()
