import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services import web_files


def _site(data_path: str, disk_mb: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=4, data_path=data_path, disk_mb=disk_mb)


class FakeUpload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self.file = io.BytesIO(data)


class WebFilesTests(unittest.TestCase):
    def test_safe_path_rejects_parent_and_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "1"
            ten = Path(tmp) / "10"
            (one / "public").mkdir(parents=True)
            (ten / "public").mkdir(parents=True)
            (ten / "public" / "secret.txt").write_text("nope", encoding="utf-8")
            site = _site(str(one))
            inside = web_files._safe_path(site, "index.html")
            self.assertEqual(inside, (one / "public" / "index.html").resolve())
            with self.assertRaises(HTTPException) as traversal:
                web_files._safe_path(site, "../10/public/secret.txt")
            self.assertEqual(traversal.exception.status_code, 400)

    def test_quota_blocks_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = _site(tmp, disk_mb=1)
            public = Path(tmp) / "public"
            public.mkdir()
            (public / "a.txt").write_bytes(b"12345")
            with patch.object(web_files, "max_edit_bytes", return_value=100), patch.object(
                web_files, "quota_bytes", return_value=8
            ):
                with self.assertRaises(HTTPException) as raised:
                    web_files.write_file(site, "b.txt", "zzzzzz")
                self.assertEqual(raised.exception.status_code, 400)
                self.assertFalse((public / "b.txt").exists())

    def test_upload_rejects_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = _site(tmp)
            (Path(tmp) / "public").mkdir()
            with patch.object(web_files, "max_upload_bytes", return_value=8), patch.object(
                web_files, "quota_bytes", return_value=1000
            ):
                with self.assertRaises(HTTPException) as raised:
                    web_files.upload_file(site, "", FakeUpload("big.bin", b"0123456789"))
                self.assertEqual(raised.exception.status_code, 413)

    def test_create_directory_and_nested_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = _site(tmp, disk_mb=10)
            created = web_files.create_directory(site, "", "assets")
            self.assertTrue(created["is_dir"])
            self.assertEqual(created["path"], "assets")
            uploaded = web_files.upload_file(
                site,
                "",
                FakeUpload("assets/css/style.css", b"body{}"),
            )
            self.assertEqual(uploaded["path"], "assets/css/style.css")
            items = web_files.list_directory(site, "assets")
            self.assertTrue(any(item["name"] == "css" and item["is_dir"] for item in items))

    def test_delete_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = _site(tmp, disk_mb=10)
            public = Path(tmp) / "public"
            public.mkdir()
            (public / "old.txt").write_text("bye", encoding="utf-8")
            web_files.create_directory(site, "", "tmp")
            web_files.delete_path(site, "old.txt")
            self.assertFalse((public / "old.txt").exists())
            web_files.delete_path(site, "tmp")
            self.assertFalse((public / "tmp").exists())

    def test_cannot_delete_public_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = _site(tmp)
            (Path(tmp) / "public").mkdir()
            with self.assertRaises(HTTPException) as raised:
                web_files.delete_path(site, "")
            self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
