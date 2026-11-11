import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.models.cloud_file import CloudFile
from app.models.cloud_storage_order import CloudStorageOrder
from app.models.game_server import GameOrder, GameServer
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder
from app.services.admin_management import (
    _assert_can_delete_account,
    _purge_game_data,
    collect_deletion_preview,
    delete_user_account,
)


class _Query:
    def __init__(self, *, rows=None, count=0):
        self._rows = rows or []
        self._count = count

    def filter(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def count(self):
        return self._count

    def delete(self, *args, **kwargs):
        return 0

    def update(self, *args, **kwargs):
        return 0


class AdminDeleteAccountTests(unittest.TestCase):
    def test_cannot_delete_self(self) -> None:
        admin = SimpleNamespace(id=7)
        user = SimpleNamespace(id=7, phone="11999999999", is_admin=True)
        with self.assertRaises(HTTPException) as raised:
            _assert_can_delete_account(MagicMock(), admin, user, "11999999999")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("própria", raised.exception.detail)

    def test_cannot_delete_last_active_admin(self) -> None:
        admin = SimpleNamespace(id=1)
        user = SimpleNamespace(id=2, phone="11988887777", is_admin=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 0
        with self.assertRaises(HTTPException) as raised:
            _assert_can_delete_account(db, admin, user, "11988887777")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("último administrador", raised.exception.detail)

    def test_phone_must_match(self) -> None:
        admin = SimpleNamespace(id=1)
        user = SimpleNamespace(id=2, phone="11988887777", is_admin=False)
        with self.assertRaises(HTTPException) as raised:
            _assert_can_delete_account(MagicMock(), admin, user, "11900000000")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("telefone", raised.exception.detail.lower())

    @patch("app.services.admin_management.used_bytes", return_value=2048)
    def test_preview_lists_vms_cloud_and_games(self, _used) -> None:
        user = SimpleNamespace(
            id=4,
            name="Cliente",
            phone="11977776666",
            email="cli@example.com",
            is_admin=False,
            created_at=datetime(2026, 1, 2),
        )
        vm = SimpleNamespace(
            id=11,
            vm_name="web-01",
            status=SimpleNamespace(value="running"),
            ip_address="192.168.0.201",
            vcpu=2,
            ram_mb=4096,
            disk_gb=40,
        )
        game = SimpleNamespace(
            id=21,
            server_name="survival",
            game_type=SimpleNamespace(value="minecraft"),
            status=SimpleNamespace(value="running"),
            port=25565,
        )
        db = MagicMock()
        db.get.return_value = user

        def query(model):
            if model is VpsInstance:
                return _Query(rows=[vm], count=1)
            if model is GameServer:
                return _Query(rows=[game], count=1)
            if model is CloudFile:
                return _Query(count=3)
            if model is VpsOrder:
                return _Query(count=2)
            if model is CloudStorageOrder:
                return _Query(count=1)
            if model is GameOrder:
                return _Query(count=1)
            return _Query()

        db.query.side_effect = query
        preview = collect_deletion_preview(db, 4)
        self.assertEqual(preview["name"], "Cliente")
        self.assertEqual(preview["vps"][0]["vm_name"], "web-01")
        self.assertEqual(preview["game_servers"][0]["server_name"], "survival")
        self.assertEqual(preview["cloud"]["used_bytes"], 2048)
        self.assertTrue(any("VPS" in item for item in preview["warnings"]))
        serialized = str(preview)
        self.assertNotIn("hashed_password", serialized)

    def test_purge_game_data_stays_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "games"
            owned = root / "4" / "1"
            owned.mkdir(parents=True)
            (owned / "world.dat").write_text("ok", encoding="utf-8")
            other = Path(tmp) / "other"
            other.mkdir()
            secret = other / "secret.txt"
            secret.write_text("nope", encoding="utf-8")
            settings = SimpleNamespace(game_servers_data_path=str(root))
            with patch("app.config.get_settings", return_value=settings):
                _purge_game_data(SimpleNamespace(data_path=str(owned), host=None))
                self.assertFalse(owned.exists())
                _purge_game_data(SimpleNamespace(data_path=str(other), host=None))
                self.assertTrue(secret.exists())

    @patch("app.services.admin_management._purge_user_game_root")
    @patch("app.services.admin_management._purge_game_data")
    @patch("app.services.admin_management.delete_all_for_user", return_value=5)
    @patch("app.services.admin_management._destroy_vps_instance")
    def test_delete_destroys_vms_then_removes_user(
        self, destroy_vm, delete_cloud, _purge_data, _purge_root
    ) -> None:
        admin = SimpleNamespace(id=1)
        user = SimpleNamespace(
            id=9,
            phone="11955554444",
            email="gone@example.com",
            is_admin=False,
            name="Alvo",
        )
        instance = SimpleNamespace(id=3, vm_name="box-9", status="running")
        db = MagicMock()
        db.get.return_value = user

        def query(model):
            if model is VpsInstance:
                return _Query(rows=[instance])
            if model is User:
                q = _Query(count=1)
                q.filter = MagicMock(return_value=q)
                q.count = MagicMock(return_value=1)
                return q
            return _Query()

        db.query.side_effect = query
        result = delete_user_account(db, admin, 9, "11955554444")
        destroy_vm.assert_called_once_with(instance)
        delete_cloud.assert_called_once()
        db.delete.assert_called_once_with(user)
        db.commit.assert_called_once()
        self.assertEqual(result["deleted_user_id"], 9)
        self.assertEqual(result["destroyed_vms"], ["box-9"])
        self.assertEqual(result["deleted_cloud_files"], 5)

    @patch("app.services.admin_management.delete_all_for_user")
    @patch(
        "app.services.admin_management._destroy_vps_instance",
        side_effect=RuntimeError("esxi down"),
    )
    def test_delete_aborts_when_vm_destroy_fails(self, destroy_vm, delete_cloud) -> None:
        admin = SimpleNamespace(id=1)
        user = SimpleNamespace(id=9, phone="11955554444", email=None, is_admin=False)
        instance = SimpleNamespace(id=3, vm_name="box-9", status="running")
        db = MagicMock()
        db.get.return_value = user
        db.query.side_effect = lambda model: _Query(rows=[instance] if model is VpsInstance else [])
        with self.assertRaises(HTTPException) as raised:
            delete_user_account(db, admin, 9, "11955554444")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("box-9", raised.exception.detail)
        delete_cloud.assert_not_called()
        db.delete.assert_not_called()
        db.commit.assert_not_called()
        destroy_vm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
