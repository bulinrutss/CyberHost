import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.game_sandbox import (
    is_allowed_executable,
    is_safe_cwd,
    parse_unit_server_id,
    unit_name,
)
from app.services import game_process


class GameSandboxTests(unittest.TestCase):
    def test_unit_name_is_prefixed_and_numeric(self) -> None:
        self.assertEqual(unit_name(7), "cyberhost-game-7.service")
        self.assertEqual(parse_unit_server_id("cyberhost-game-7.service"), 7)
        with self.assertRaises(ValueError):
            parse_unit_server_id("sshd.service")
        with self.assertRaises(ValueError):
            parse_unit_server_id("cyberhost-game-../escape.service")
        with self.assertRaises(ValueError):
            unit_name(0)

    def test_cwd_must_stay_inside_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "game_servers"
            server = data / "2" / "1"
            server.mkdir(parents=True)
            self.assertTrue(is_safe_cwd(server, data))
            outside = Path(root) / "other"
            outside.mkdir()
            self.assertFalse(is_safe_cwd(outside, data))

    def test_executable_inside_server_dir_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "servers"
            data.mkdir()
            malware = data / "1" / "pwn"
            malware.parent.mkdir()
            malware.write_bytes(b"x")
            allowed = Path(root) / "bin" / "java"
            allowed.parent.mkdir()
            allowed.write_bytes(b"x")
            self.assertFalse(is_allowed_executable(malware, data, [allowed]))
            self.assertTrue(is_allowed_executable(allowed, data, [allowed]))

    def test_spawn_argv_uses_sudo_and_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "s"
            data.mkdir()
            server = SimpleNamespace(id=9, ram_mb=512, data_path=str(data))
            settings = SimpleNamespace(
                game_process_user="cyberhost-game",
                game_process_owner="rts",
                game_process_cpu_quota_percent=100,
                game_process_tasks_max=128,
                game_servers_data_path=str(data),
                game_samp_binary="",
                game_mta_binary="",
                game_fivem_binary="",
                game_minecraft_java="",
            )
            java = Path(root) / "java"
            java.write_bytes(b"x")
            with patch.object(game_process, "_allow_bins", return_value=[java]), patch.object(
                game_process, "_data_root", return_value=data
            ), patch.object(game_process, "sys") as sys_mod:
                sys_mod.executable = "/opt/host/backend/.venv/bin/python"
                argv = game_process._isolated_spawn_argv(
                    server, settings, [str(java), "-jar", "server.jar"], data / "log"
                )
            self.assertEqual(argv[0:2], ["sudo", "-n"])
            self.assertIn("spawn", argv)
            sep = argv.index("--")
            self.assertIn("--allow-bin", argv[:sep])
            self.assertEqual(argv[sep + 1 :], [str(java), "-jar", "server.jar"])
            self.assertNotIn(str(data / "malware"), argv)

    def test_isolation_off_on_windows_flag(self) -> None:
        settings = SimpleNamespace(game_process_isolate=True, game_process_user="cyberhost-game")
        with patch.object(game_process, "sys") as sys_mod:
            sys_mod.platform = "win32"
            self.assertFalse(game_process.isolation_enabled(settings))


if __name__ == "__main__":
    unittest.main()
