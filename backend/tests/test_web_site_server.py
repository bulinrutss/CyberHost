import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "web_site_server.py"


class WebSiteServerTests(unittest.TestCase):
    def test_rejects_non_loopback_bind(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--bind", "0.0.0.0", "--port", "30100", "--root", "."],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("127.0.0.1", result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
