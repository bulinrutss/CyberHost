import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.models.cloud_storage_order import CloudStorageOrder
from app.models.coupon import CouponRedemption
from app.models.game_server import GameOrder, GameServer
from app.models.vps import VpsInstance, VpsOrder
from app.services.admin_management import (
    clear_machine_error_event,
    delete_admin_order,
    order_can_hard_delete,
)


def _locked_get(model, row):
    query = MagicMock()
    query.filter.return_value.with_for_update.return_value.first.return_value = row
    query.filter.return_value.first.return_value = row
    query.filter.return_value.delete.return_value = 0
    query.filter.return_value.update.return_value = 1 if row else 0
    return query


class AdminDeleteOrderTests(unittest.TestCase):
    def test_rules_block_in_flight_without_machine(self) -> None:
        self.assertTrue(order_can_hard_delete("vps", "cancelled", linked=False))
        self.assertTrue(order_can_hard_delete("vps", "failed", linked=False))
        self.assertTrue(order_can_hard_delete("cloud", "paid", linked=False))
        self.assertTrue(order_can_hard_delete("vps", "active", linked=True))
        self.assertTrue(order_can_hard_delete("vps", "paid", linked=True))
        self.assertFalse(order_can_hard_delete("vps", "paid", linked=False))
        self.assertFalse(order_can_hard_delete("game", "provisioning", linked=False))

    def test_delete_cancelled_vps_releases_coupon_row(self) -> None:
        order = SimpleNamespace(id=5, status="cancelled", coupon_id=None)
        db = MagicMock()

        def query(model):
            if model is VpsOrder:
                return _locked_get(model, order)
            if model is VpsInstance:
                return _locked_get(model, None)
            if model is CouponRedemption:
                return _locked_get(model, None)
            return _locked_get(model, None)

        db.query.side_effect = query
        delete_admin_order(db, "vps", 5)
        db.delete.assert_called_once_with(order)
        db.commit.assert_called_once()

    def test_delete_linked_vps_unlinks_then_deletes(self) -> None:
        order = SimpleNamespace(id=5, status="active", coupon_id=None)
        db = MagicMock()

        def query(model):
            if model is VpsOrder:
                return _locked_get(model, order)
            if model is VpsInstance:
                return _locked_get(model, SimpleNamespace(id=9, order_id=5))
            if model is CouponRedemption:
                return _locked_get(model, None)
            return _locked_get(model, None)

        db.query.side_effect = query
        delete_admin_order(db, "vps", 5)
        inst_query = [call for call in db.query.call_args_list if call.args and call.args[0] is VpsInstance]
        self.assertTrue(inst_query)
        db.delete.assert_called_once_with(order)
        db.commit.assert_called_once()

    def test_delete_cloud_order(self) -> None:
        order = SimpleNamespace(id=8, status="cancelled")
        db = MagicMock()

        def query(model):
            if model is CloudStorageOrder:
                return _locked_get(model, order)
            return _locked_get(model, None)

        db.query.side_effect = query
        delete_admin_order(db, "cloud", 8)
        db.delete.assert_called_once_with(order)
        db.commit.assert_called_once()

    def test_delete_game_order_unlinks_server(self) -> None:
        order = SimpleNamespace(id=3, status="failed")
        db = MagicMock()

        def query(model):
            if model is GameOrder:
                return _locked_get(model, order)
            if model is GameServer:
                return _locked_get(model, SimpleNamespace(id=1, order_id=3))
            return _locked_get(model, None)

        db.query.side_effect = query
        delete_admin_order(db, "game", 3)
        db.delete.assert_called_once_with(order)
        db.commit.assert_called_once()

    @patch("app.services.coupons.release_coupon_reservation")
    def test_delete_pending_vps_releases_coupon(self, release) -> None:
        order = SimpleNamespace(id=12, status="pending_payment", coupon_id=4)
        db = MagicMock()

        def query(model):
            if model is VpsOrder:
                return _locked_get(model, order)
            if model is VpsInstance:
                return _locked_get(model, None)
            if model is CouponRedemption:
                return _locked_get(model, None)
            return _locked_get(model, None)

        db.query.side_effect = query
        delete_admin_order(db, "vps", 12)
        release.assert_called_once_with(db, 12, 4)
        db.delete.assert_called_once_with(order)

    def test_clear_machine_error(self) -> None:
        instance = SimpleNamespace(
            id=9,
            status="running",
            error_message="alerta antigo",
            suspended_for_billing=False,
        )
        db = MagicMock()
        db.get.return_value = instance
        clear_machine_error_event(db, 9)
        self.assertIsNone(instance.error_message)
        db.commit.assert_called_once()

    def test_clear_machine_error_rejects_live_fault(self) -> None:
        instance = SimpleNamespace(
            id=9,
            status="error",
            error_message="clone timeout",
            suspended_for_billing=False,
        )
        db = MagicMock()
        db.get.return_value = instance
        with self.assertRaises(HTTPException) as raised:
            clear_machine_error_event(db, 9)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(instance.error_message, "clone timeout")


if __name__ == "__main__":
    unittest.main()
