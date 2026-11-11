import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.web_provisioner import allocate_port


class _PortQuery:
    def __init__(self, ports: list[int]):
        self._ports = ports

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [(port,) for port in self._ports]


class WebPortTests(unittest.TestCase):
    def test_skips_used_ports_in_pool(self) -> None:
        db = MagicMock()
        db.query.return_value = _PortQuery([30000, 30001])
        settings = SimpleNamespace(web_port_range_start=30000, web_port_range_end=30005)
        with patch("app.services.web_provisioner.get_settings", return_value=settings):
            self.assertEqual(allocate_port(db), 30002)

    def test_raises_when_pool_exhausted(self) -> None:
        db = MagicMock()
        db.query.return_value = _PortQuery([30000, 30001])
        settings = SimpleNamespace(web_port_range_start=30000, web_port_range_end=30001)
        with patch("app.services.web_provisioner.get_settings", return_value=settings):
            with self.assertRaises(ValueError):
                allocate_port(db)

    def test_query_ignores_deleted_sites(self) -> None:
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = _PortQuery([])
        settings = SimpleNamespace(web_port_range_start=30000, web_port_range_end=30000)
        with patch("app.services.web_provisioner.get_settings", return_value=settings):
            self.assertEqual(allocate_port(db), 30000)
        query.filter.assert_called_once()


if __name__ == "__main__":
    unittest.main()
