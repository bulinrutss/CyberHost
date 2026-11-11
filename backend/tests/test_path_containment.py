import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.game_files import _safe_path
from app.services.game_sandbox import is_under_root


def _server(data_path: str) -> SimpleNamespace:
    return SimpleNamespace(id=1, data_path=data_path)


class PathContainmentTests(unittest.TestCase):
    def test_is_relative_to_rejects_sibling_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "1"
            ten = Path(tmp) / "10"
            one.mkdir()
            ten.mkdir()
            secret = ten / "secret.txt"
            secret.write_text("nope", encoding="utf-8")
            escaped = (one / ".." / "10" / "secret.txt").resolve()
            root = one.resolve()
            self.assertTrue(str(escaped).startswith(str(root)))
            self.assertFalse(escaped.is_relative_to(root))
            self.assertFalse(is_under_root(escaped, root))

    def test_safe_path_rejects_parent_and_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "1"
            ten = Path(tmp) / "10"
            one.mkdir()
            ten.mkdir()
            (ten / "secret.txt").write_text("nope", encoding="utf-8")
            (one / "ok.txt").write_text("yes", encoding="utf-8")
            server = _server(str(one))
            inside = _safe_path(server, "ok.txt")
            self.assertEqual(inside, (one / "ok.txt").resolve())
            with self.assertRaises(HTTPException) as traversal:
                _safe_path(server, "../10/secret.txt")
            self.assertEqual(traversal.exception.status_code, 400)

    def test_safe_path_allows_root_listing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "srv"
            root.mkdir()
            server = _server(str(root))
            self.assertEqual(_safe_path(server, ""), root.resolve())
            self.assertEqual(_safe_path(server, "."), root.resolve())


if __name__ == "__main__":
    unittest.main()
