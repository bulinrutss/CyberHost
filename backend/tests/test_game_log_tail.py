import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import game_process


class GameLogTailTests(unittest.TestCase):
    def test_missing_file_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(game_process.tail_logs(root, 20), "")

    def test_returns_only_last_lines(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / game_process.LOG_FILE
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(f"line-{i}" for i in range(200)), encoding="utf-8")
            text = game_process.tail_logs(root, 5)
            self.assertEqual(text, "line-195\nline-196\nline-197\nline-198\nline-199")

    def test_reads_in_bounded_blocks_not_the_whole_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / game_process.LOG_FILE
            path.parent.mkdir(parents=True)
            marker = "HEAD-UNIQUE-MARKER"
            path.write_bytes(
                marker.encode("utf-8")
                + b"\n"
                + (b"x" * 20000)
                + b"\nTAIL-LINE-1\nTAIL-LINE-2\n"
            )
            with patch.object(game_process, "LOG_TAIL_MAX_BYTES", 4096):
                with patch.object(game_process, "LOG_TAIL_CHUNK_BYTES", 512):
                    text = game_process.tail_logs(root, 2)
            self.assertNotIn(marker, text)
            self.assertTrue(text.endswith("TAIL-LINE-1\nTAIL-LINE-2"))
            self.assertLessEqual(len(text.encode("utf-8")), 4096)

    def test_caps_line_count(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / game_process.LOG_FILE
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(f"n{i}" for i in range(800)), encoding="utf-8")
            text = game_process.tail_logs(root, 10_000)
            self.assertEqual(len(text.splitlines()), game_process.LOG_TAIL_MAX_LINES)

    def test_rotate_copytruncates_and_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / game_process.LOG_FILE
            path.parent.mkdir(parents=True)
            path.write_bytes(b"old-log\n" + (b"y" * 2000))
            rotated = game_process.rotate_game_log(path, max_bytes=1000, keep=2)
            self.assertTrue(rotated)
            self.assertEqual(path.stat().st_size, 0)
            backup = path.with_name(path.name + ".1")
            self.assertTrue(backup.is_file())
            self.assertGreater(backup.stat().st_size, 1000)
            self.assertTrue(backup.read_bytes().startswith(b"old-log\n"))

    def test_tail_rotates_after_returning_last_lines(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / game_process.LOG_FILE
            path.parent.mkdir(parents=True)
            path.write_text("keep-me\n" + ("z" * 500) + "\nend\n", encoding="utf-8")
            with patch.object(game_process, "LOG_ROTATE_MAX_BYTES", 100):
                text = game_process.tail_logs(root, 2)
            self.assertIn("end", text)
            self.assertEqual(path.stat().st_size, 0)
            self.assertTrue(path.with_name(path.name + ".1").is_file())
