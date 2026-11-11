import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.cloud_files import (
    assert_upload_concurrency,
    assert_upload_quota,
    expected_chunk_size,
    reserved_bytes,
    uploading_count,
    used_bytes,
)


class CloudUploadQuotaTests(unittest.TestCase):
    def test_expected_last_chunk_matches_reservation(self) -> None:
        chunk = 10
        self.assertEqual(expected_chunk_size(25, 3, 0, chunk), 10)
        self.assertEqual(expected_chunk_size(25, 3, 1, chunk), 10)
        self.assertEqual(expected_chunk_size(25, 3, 2, chunk), 5)
        self.assertEqual(expected_chunk_size(10, 1, 0, chunk), 10)

    def test_expected_rejects_out_of_range(self) -> None:
        self.assertEqual(expected_chunk_size(25, 3, 3, 10), 0)
        self.assertEqual(expected_chunk_size(0, 1, 0, 10), 0)

    def test_quota_counts_incomplete_reservation(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            assert_upload_quota(used=90, incoming=20, limit=100)
        self.assertEqual(raised.exception.status_code, 400)
        assert_upload_quota(used=80, incoming=20, limit=100)

    def test_concurrency_cap(self) -> None:
        assert_upload_concurrency(active=4, max_allowed=5)
        with self.assertRaises(HTTPException) as raised:
            assert_upload_concurrency(active=5, max_allowed=5)
        self.assertEqual(raised.exception.status_code, 429)

    def test_used_bytes_includes_uploading_rows(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [(100,), (50,)]
        self.assertEqual(used_bytes(db, 7), 150)

    def test_used_bytes_can_exclude_resumed_file(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = [(40,)]
        self.assertEqual(used_bytes(db, 7, exclude_file_id=3), 40)

    def test_reserved_and_count_queries(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [(12,)]
        db.query.return_value.filter.return_value.count.return_value = 2
        self.assertEqual(reserved_bytes(db, 7), 12)
        self.assertEqual(uploading_count(db, 7), 2)


if __name__ == "__main__":
    unittest.main()
