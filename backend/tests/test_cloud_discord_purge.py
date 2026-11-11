import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.cloud_file import CloudDiscordTombstone, CloudFile, CloudFileChunk
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.services.cloud_discord_purge import purge_discord_tombstones
from app.services.cloud_files import delete_node


class CloudDiscordTombstoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                CloudFile.__table__,
                CloudFileChunk.__table__,
                CloudDiscordTombstone.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11970001111",
            name="Cloud",
            hashed_password="x",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.settings_patch = patch(
            "app.services.cloud_files._settings",
            return_value=SimpleNamespace(cloud_files_path=self.tmp.name),
        )
        self.schedule_patch = patch("app.services.cloud_files.schedule_discord_purge")
        self.settings_patch.start()
        self.schedule_mock = self.schedule_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        self.schedule_patch.stop()
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def _discord_file(self, *, name: str = "a.bin") -> CloudFile:
        record = CloudFile(
            user_id=self.user.id,
            name=name,
            is_folder=False,
            size_bytes=10,
            chunk_count=2,
            storage_backend="discord",
            upload_status="ready",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        self.db.add_all(
            [
                CloudFileChunk(
                    file_id=record.id,
                    chunk_index=0,
                    size_bytes=5,
                    discord_channel_id="111",
                    discord_message_id="m-0",
                    discord_bot_index=0,
                ),
                CloudFileChunk(
                    file_id=record.id,
                    chunk_index=1,
                    size_bytes=5,
                    discord_channel_id="111",
                    discord_message_id="m-1",
                    discord_bot_index=1,
                ),
            ]
        )
        self.db.commit()
        return record

    def test_delete_queues_tombstones_and_hides_file(self) -> None:
        record = self._discord_file()
        file_id = record.id
        delete_node(self.db, self.user, file_id)
        self.assertIsNone(self.db.get(CloudFile, file_id))
        stones = self.db.query(CloudDiscordTombstone).all()
        self.assertEqual(len(stones), 2)
        ids = {row.discord_message_id for row in stones}
        self.assertEqual(ids, {"m-0", "m-1"})
        self.schedule_mock.assert_called_once()

    def test_local_file_has_no_tombstone(self) -> None:
        record = CloudFile(
            user_id=self.user.id,
            name="local.bin",
            is_folder=False,
            size_bytes=4,
            chunk_count=1,
            storage_backend="local",
            upload_status="ready",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        self.db.add(
            CloudFileChunk(file_id=record.id, chunk_index=0, size_bytes=4)
        )
        self.db.commit()
        delete_node(self.db, self.user, record.id)
        self.assertEqual(self.db.query(CloudDiscordTombstone).count(), 0)

    def test_purge_removes_tombstone_only_after_discord_gone(self) -> None:
        record = self._discord_file()
        delete_node(self.db, self.user, record.id)
        storage = MagicMock()
        storage.try_delete_message.side_effect = [False, True, True]
        with patch(
            "app.services.cloud_discord_purge.get_discord_storage",
            return_value=storage,
        ):
            first = purge_discord_tombstones(self.db, limit=10)
            self.assertEqual(first, 1)
            remaining = self.db.query(CloudDiscordTombstone).all()
            self.assertEqual(len(remaining), 1)
            self.assertGreaterEqual(remaining[0].attempts, 1)
            remaining[0].next_retry_at = remaining[0].next_retry_at.replace(year=2000)
            self.db.commit()
            second = purge_discord_tombstones(self.db, limit=10)
            self.assertEqual(second, 1)
            self.assertEqual(self.db.query(CloudDiscordTombstone).count(), 0)

    def test_folder_delete_tombs_nested_discord_files(self) -> None:
        folder = CloudFile(
            user_id=self.user.id,
            name="pasta",
            is_folder=True,
            upload_status="ready",
        )
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        child = self._discord_file(name="nested.bin")
        child.parent_id = folder.id
        self.db.commit()
        delete_node(self.db, self.user, folder.id)
        self.assertIsNone(self.db.get(CloudFile, folder.id))
        self.assertIsNone(self.db.get(CloudFile, child.id))
        self.assertEqual(self.db.query(CloudDiscordTombstone).count(), 2)
