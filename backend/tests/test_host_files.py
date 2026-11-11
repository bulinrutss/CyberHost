import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services import host_files
from app.services.host_shell import build_shell_env


def _settings(root: str) -> SimpleNamespace:
    return SimpleNamespace(
        host_files_roots=root,
        host_file_root_list=[root],
        host_files_max_edit_bytes=2 * 1024 * 1024,
        host_files_max_upload_bytes=50 * 1024 * 1024,
    )


class HostFilesContainmentTests(unittest.TestCase):
    def test_rejects_sibling_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            allowed = Path(tmp) / "opt-host"
            secret = Path(tmp) / "secret"
            allowed.mkdir()
            secret.mkdir()
            (secret / "keys.env").write_text("NOPE", encoding="utf-8")
            (allowed / "ok.txt").write_text("yes", encoding="utf-8")
            settings = _settings(str(allowed))
            with patch("app.services.host_files.get_settings", return_value=settings):
                inside = host_files.resolve_host_path(str(allowed / "ok.txt"), settings)
                self.assertEqual(inside, (allowed / "ok.txt").resolve())
                with self.assertRaises(HTTPException) as escaped:
                    host_files.resolve_host_path(str(secret / "keys.env"), settings)
                self.assertEqual(escaped.exception.status_code, 400)
                with self.assertRaises(HTTPException):
                    host_files.resolve_host_path(str(allowed / ".." / "secret" / "keys.env"), settings)

    def test_list_empty_returns_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "host"
            root.mkdir()
            settings = _settings(str(root))
            with patch("app.services.host_files.get_settings", return_value=settings):
                listing = host_files.list_directory("", settings)
                self.assertEqual(listing["path"], "")
                self.assertEqual(len(listing["entries"]), 1)
                self.assertEqual(listing["entries"][0]["path"], str(root.resolve()))

    def test_write_read_and_invalid_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "host"
            root.mkdir()
            settings = _settings(str(root))
            with patch("app.services.host_files.get_settings", return_value=settings):
                target = str(root / "note.txt")
                host_files.write_file(target, "olá", settings)
                data = host_files.read_file(target, settings)
                self.assertEqual(data["content"], "olá")
                with self.assertRaises(HTTPException):
                    host_files.assert_child_name("../x")
                with self.assertRaises(HTTPException):
                    host_files.mkdir(str(root), "a/b", settings)

    def test_cannot_delete_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "host"
            root.mkdir()
            settings = _settings(str(root))
            with patch("app.services.host_files.get_settings", return_value=settings):
                with self.assertRaises(HTTPException) as raised:
                    host_files.delete_entry(str(root), settings)
                self.assertEqual(raised.exception.status_code, 400)


class HostShellEnvTests(unittest.TestCase):
    def test_shell_env_drops_secrets(self) -> None:
        fake = {
            "SECRET_KEY": "super-secret",
            "DATABASE_URL": "mysql://x",
            "ESXI_PASSWORD": "pw",
            "ABACATEPAY_API_KEY": "key",
            "PATH": "/usr/bin",
            "HOME": "/home/rts",
            "USER": "rts",
        }
        with patch.dict(os.environ, fake, clear=True):
            env = build_shell_env(cwd="/opt/host")
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertNotIn("SECRET_KEY", env)
        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("ESXI_PASSWORD", env)
        self.assertNotIn("ABACATEPAY_API_KEY", env)
        dumped = " ".join(env.values())
        self.assertNotIn("super-secret", dumped)

    def test_pty_read_ignores_would_block(self) -> None:
        from unittest.mock import patch

        from app.services.host_shell import read_pty_chunk

        with patch("app.services.host_shell.os.read", side_effect=BlockingIOError):
            self.assertIsNone(read_pty_chunk(3))
        with patch("app.services.host_shell.os.read", return_value=b"hi"):
            self.assertEqual(read_pty_chunk(3), b"hi")
        with patch("app.services.host_shell.os.read", return_value=b""):
            self.assertEqual(read_pty_chunk(3), b"")
