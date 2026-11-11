import os
import stat
import tempfile
import unittest
from pathlib import Path

from app.services.web_sandbox import ensure_web_runtime_visible_to_isolated_user


class WebSandboxRuntimeTests(unittest.TestCase):
    def test_noop_when_not_root(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("teste cobre apenas ambiente sem root")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backend"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            server = scripts / "web_site_server.py"
            server.write_text("print('ok')", encoding="utf-8")
            os.chmod(root, 0o700)
            os.chmod(scripts, 0o700)
            os.chmod(server, 0o600)
            ensure_web_runtime_visible_to_isolated_user(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(server.stat().st_mode & 0o777, 0o600)

    def test_adds_traverse_when_root(self) -> None:
        if os.geteuid() != 0:
            self.skipTest("requer root para chmod de traverse")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backend"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            server = scripts / "web_site_server.py"
            server.write_text("print('ok')", encoding="utf-8")
            os.chmod(root, 0o700)
            os.chmod(scripts, 0o700)
            os.chmod(server, 0o600)
            ensure_web_runtime_visible_to_isolated_user(root)
            self.assertTrue(root.stat().st_mode & stat.S_IXOTH)
            self.assertTrue(scripts.stat().st_mode & stat.S_IXOTH)
            self.assertTrue(server.stat().st_mode & stat.S_IROTH)


if __name__ == "__main__":
    unittest.main()
