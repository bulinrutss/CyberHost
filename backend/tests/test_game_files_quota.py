import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services import game_files


def _server(data_path: str) -> SimpleNamespace:
    return SimpleNamespace(id=3, data_path=data_path)


class FakeUpload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self.file = io.BytesIO(data)


class GameFilesQuotaTests(unittest.TestCase):
    def test_edit_rejects_oversize_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            with patch.object(game_files, "max_edit_bytes", return_value=8), patch.object(
                game_files, "quota_bytes", return_value=1000
            ):
                with self.assertRaises(HTTPException) as raised:
                    game_files.write_file(server, "server.cfg", "x" * 16)
                self.assertEqual(raised.exception.status_code, 413)

    def test_edit_counts_utf8_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            with patch.object(game_files, "max_edit_bytes", return_value=3), patch.object(
                game_files, "quota_bytes", return_value=1000
            ):
                with self.assertRaises(HTTPException) as raised:
                    game_files.write_file(server, "motd.txt", "áá")
                self.assertEqual(raised.exception.status_code, 413)

    def test_quota_blocks_new_write(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            Path(root, "a.txt").write_bytes(b"12345")
            with patch.object(game_files, "max_edit_bytes", return_value=100), patch.object(
                game_files, "quota_bytes", return_value=8
            ):
                with self.assertRaises(HTTPException) as raised:
                    game_files.write_file(server, "b.txt", "zzzzzz")
                self.assertEqual(raised.exception.status_code, 400)
                self.assertFalse(Path(root, "b.txt").exists())

    def test_overwrite_uses_size_delta(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            Path(root, "a.txt").write_bytes(b"12345")
            with patch.object(game_files, "max_edit_bytes", return_value=100), patch.object(
                game_files, "quota_bytes", return_value=8
            ):
                game_files.write_file(server, "a.txt", "abcd")
                self.assertEqual(Path(root, "a.txt").read_text(encoding="utf-8"), "abcd")

    def test_tree_used_ignores_internal_dir(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            Path(root, "visible.bin").write_bytes(b"ab")
            internal = Path(root, ".cyberhost")
            internal.mkdir()
            (internal / "state.json").write_bytes(b"x" * 50)
            self.assertEqual(game_files.tree_used_bytes(server), 2)

    def test_upload_rejects_over_file_limit(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            with patch.object(game_files, "max_upload_bytes", return_value=16), patch.object(
                game_files, "quota_bytes", return_value=1000
            ):
                with self.assertRaises(HTTPException) as raised:
                    game_files.upload_file(server, "", FakeUpload("big.bin", b"x" * 32))
                self.assertEqual(raised.exception.status_code, 413)
                self.assertFalse(Path(root, "big.bin").exists())
                self.assertFalse(Path(root, "big.bin.part").exists())

    def test_upload_rejects_over_quota(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            Path(root, "keep.bin").write_bytes(b"x" * 20)
            with patch.object(game_files, "max_upload_bytes", return_value=100), patch.object(
                game_files, "quota_bytes", return_value=24
            ):
                with self.assertRaises(HTTPException) as raised:
                    game_files.upload_file(server, "", FakeUpload("more.bin", b"yyyyyy"))
                self.assertEqual(raised.exception.status_code, 413)
                self.assertFalse(Path(root, "more.bin").exists())

    def test_upload_writes_within_limits(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            with patch.object(game_files, "max_upload_bytes", return_value=64), patch.object(
                game_files, "quota_bytes", return_value=64
            ):
                result = game_files.upload_file(server, "", FakeUpload("ok.bin", b"hello"))
                self.assertEqual(result["name"], "ok.bin")
                self.assertEqual(result["size_bytes"], 5)
                self.assertEqual(Path(root, "ok.bin").read_bytes(), b"hello")


if __name__ == "__main__":
    unittest.main()
