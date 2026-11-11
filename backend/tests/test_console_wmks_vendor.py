import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "frontend/src/components/VpsConsolePanel.tsx"
VENDOR = ROOT / "frontend/public/wmks/vendor"


class ConsoleWmksVendorTests(unittest.TestCase):
    def test_console_does_not_load_remote_jquery(self) -> None:
        src = CONSOLE.read_text(encoding="utf-8")
        self.assertNotIn("code.jquery.com", src)
        self.assertIn("/wmks/vendor/jquery-3.7.1.min.js", src)
        self.assertIn("/wmks/vendor/jquery-ui-1.13.2.min.js", src)

    def test_vendor_jquery_files_exist(self) -> None:
        jquery = VENDOR / "jquery-3.7.1.min.js"
        ui = VENDOR / "jquery-ui-1.13.2.min.js"
        self.assertTrue(jquery.is_file(), "jquery vendor file missing")
        self.assertTrue(ui.is_file(), "jquery-ui vendor file missing")
        self.assertGreater(jquery.stat().st_size, 20_000)
        self.assertGreater(ui.stat().st_size, 50_000)
        self.assertIn(b"jQuery", jquery.read_bytes()[:120])
