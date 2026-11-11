import io
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.services.bandwidth_limiter import EmptyTransfer, TransferLimitExceeded, iter_capped, stream_to_path


class CountingReader:
    def __init__(self, total: int, block: int = 64) -> None:
        self.remaining = total
        self.block = block
        self.reads = 0
        self.max_read = 0

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        n = self.remaining if size < 0 else min(size, self.remaining, self.block)
        self.remaining -= n
        self.reads += 1
        self.max_read = max(self.max_read, n)
        return b"x" * n


class CloudChunkStreamingTests(unittest.TestCase):
    def test_stream_writes_capped_file_without_joining_body(self) -> None:
        reader = CountingReader(200, block=32)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "chunk_000000"
            written = stream_to_path(reader, dest, max_bytes=200, chunk_size=32)
            self.assertEqual(written, 200)
            self.assertEqual(dest.read_bytes(), b"x" * 200)
            self.assertGreater(reader.reads, 1)
            self.assertLessEqual(reader.max_read, 32)
            self.assertFalse(dest.with_name("chunk_000000.part").exists())

    def test_stream_rejects_overflow_and_removes_partial(self) -> None:
        reader = CountingReader(50, block=16)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "chunk_000001"
            with self.assertRaises(TransferLimitExceeded) as raised:
                stream_to_path(reader, dest, max_bytes=32, chunk_size=16)
            self.assertEqual(raised.exception.max_bytes, 32)
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_name("chunk_000001.part").exists())

    def test_stream_rejects_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "chunk_000002"
            with self.assertRaises(EmptyTransfer):
                stream_to_path(io.BytesIO(b""), dest, max_bytes=32)
            self.assertFalse(dest.exists())

    def test_iter_capped_stops_without_accumulating(self) -> None:
        blocks = [b"aa", b"bb", b"cccc"]
        out = []
        with self.assertRaises(TransferLimitExceeded):
            for block in iter_capped(iter(blocks), max_bytes=5):
                out.append(block)
        self.assertEqual(out, [b"aa", b"bb"])

    def test_save_chunk_stream_maps_overflow_to_413(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services import cloud_files as svc

        record = MagicMock()
        record.upload_status = "uploading"
        record.chunk_count = 2
        record.size_bytes = 32
        record.name = "video.bin"
        user = MagicMock()
        user.id = 9
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = record

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(svc, "chunk_size_bytes", return_value=16), patch.object(
                svc, "_chunk_path", return_value=Path(tmp) / "chunk_000000"
            ), patch.object(svc, "_file_dir"), patch.object(svc, "_uses_discord", return_value=False):
                with self.assertRaises(HTTPException) as raised:
                    svc.save_chunk_stream(db, user, 1, 0, io.BytesIO(b"x" * 32))
                self.assertEqual(raised.exception.status_code, 413)

    def test_save_chunk_stream_writes_and_records_size(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services import cloud_files as svc

        record = MagicMock()
        record.upload_status = "uploading"
        record.chunk_count = 2
        record.size_bytes = 75
        record.name = "video.bin"
        user = MagicMock()
        user.id = 9
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = record

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "chunk_000000"
            with patch.object(svc, "chunk_size_bytes", return_value=64), patch.object(
                svc, "_chunk_path", return_value=dest
            ), patch.object(svc, "_file_dir"), patch.object(
                svc, "_uses_discord", return_value=False
            ), patch.object(svc, "_upsert_chunk_record") as upsert:
                needs_discord, written = svc.save_chunk_stream(
                    db, user, 1, 0, io.BytesIO(b"hello-chunk")
                )
                self.assertFalse(needs_discord)
                self.assertEqual(written, 11)
                self.assertEqual(dest.read_bytes(), b"hello-chunk")
                upsert.assert_called_once_with(db, 1, 0, 11, reset_discord=False)

    def test_save_chunk_stream_caps_last_chunk_to_reserved_size(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services import cloud_files as svc

        record = MagicMock()
        record.upload_status = "uploading"
        record.chunk_count = 1
        record.size_bytes = 10
        record.name = "tiny.bin"
        user = MagicMock()
        user.id = 9
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = record

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(svc, "chunk_size_bytes", return_value=64), patch.object(
                svc, "_chunk_path", return_value=Path(tmp) / "chunk_000000"
            ), patch.object(svc, "_file_dir"), patch.object(svc, "_uses_discord", return_value=False):
                with self.assertRaises(HTTPException) as raised:
                    svc.save_chunk_stream(db, user, 1, 0, io.BytesIO(b"x" * 32))
                self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
