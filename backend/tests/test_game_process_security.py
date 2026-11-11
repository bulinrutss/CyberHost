import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.models.game_server import GameServerStatus, GameType
from app.services import game_process
from app.services.game_files import _safe_path


def _server(data_path: str, *, process_pid: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        data_path=data_path,
        process_pid=process_pid,
        status=GameServerStatus.RUNNING,
        game_type=GameType.SAMP,
        port=27015,
        slots=32,
        ram_mb=1024,
        server_name="Security test",
    )


class GameProcessSecurityTests(unittest.TestCase):
    def test_internal_control_directory_is_not_customer_accessible(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root)
            with self.assertRaises(HTTPException) as raised:
                _safe_path(server, ".cyberhost/state.json")
            self.assertEqual(raised.exception.status_code, 403)

    def test_forged_state_pid_is_never_signalled(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root, process_pid=None)
            state = Path(root) / game_process.STATE_FILE
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

            with patch.object(game_process.os, "kill") as kill:
                game_process.stop_server(server)

            kill.assert_not_called()

    def test_status_ignores_forged_state_pid(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root, process_pid=None)
            state = Path(root) / game_process.STATE_FILE
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

            self.assertEqual(
                game_process.sync_server_status(server),
                GameServerStatus.STOPPED,
            )

    def test_foreign_database_pid_is_not_signalled(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            server = _server(root, process_pid=4242)
            with (
                patch.object(game_process, "_is_pid_running", return_value=True),
                patch.object(game_process, "_is_managed_process", return_value=False),
                patch.object(game_process.os, "kill") as kill,
            ):
                game_process.stop_server(server)

            kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
