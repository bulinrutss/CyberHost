import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.user import User
from app.schemas.import_vms import ImportVmItem, ImportVmsRequest
from app.services.vm_import import resolve_import_user


class ImportExistingUserTests(unittest.TestCase):
    def test_schema_requires_existing_user_id_not_password(self) -> None:
        item = ImportVmItem(vm_name="VPS-cliente", user_id=7, plan_slug="vps")
        self.assertEqual(item.user_id, 7)
        with self.assertRaises(ValidationError):
            ImportVmItem(vm_name="VPS-cliente")  # type: ignore[call-arg]
        dumped = ImportVmsRequest(vms=[item]).model_dump()
        self.assertNotIn("default_password", dumped)
        self.assertNotIn("password", dumped["vms"][0])
        self.assertNotIn("phone", dumped["vms"][0])

    def test_resolve_requires_user_id(self) -> None:
        db = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            resolve_import_user(db, None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_resolve_missing_account(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            resolve_import_user(db, 99)
        self.assertEqual(ctx.exception.status_code, 404)
        db.query.assert_called_with(User)

    def test_resolve_inactive_account(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=3, is_active=False, name="Ana", phone="11999998888"
        )
        with self.assertRaises(HTTPException) as ctx:
            resolve_import_user(db, 3)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("inativa", ctx.exception.detail)

    def test_resolve_active_account(self) -> None:
        user = SimpleNamespace(id=4, is_active=True, name="Ana", phone="11999998888")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        self.assertIs(resolve_import_user(db, 4), user)
