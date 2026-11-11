import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PWA = ROOT / "frontend" / "public" / "financeiro"


class FinancePwaFilesTests(unittest.TestCase):
    def test_manifest_installs_app_without_replacing_the_website(self) -> None:
        data = json.loads((PWA / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(data["start_url"], "/financeiro")
        self.assertEqual(data["scope"], "/financeiro")
        self.assertEqual(data["display"], "standalone")
        self.assertIn("browser", data["display_override"])
        self.assertFalse(data["prefer_related_applications"])
        self.assertTrue((PWA / "icon-192.png").is_file())
        self.assertTrue((PWA / "icon-512.png").is_file())
        self.assertTrue((PWA / "apple-touch-icon.png").is_file())

    def test_service_worker_does_not_cache(self) -> None:
        sw = (PWA / "sw.js").read_text(encoding="utf-8")
        self.assertIn("fetch(event.request)", sw)
        self.assertNotIn("caches", sw)
        self.assertNotIn("cache.put", sw.lower())


class CyberHostPwaFilesTests(unittest.TestCase):
    def test_manifest_installs_panel_without_replacing_the_website(self) -> None:
        public = ROOT / "frontend" / "public"
        data = json.loads((public / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(data["start_url"], "/cyberhost/dashboard")
        self.assertEqual(data["scope"], "/cyberhost")
        self.assertEqual(data["display"], "standalone")
        self.assertIn("browser", data["display_override"])
        self.assertFalse(data["prefer_related_applications"])
        self.assertTrue((public / "pwa-icon-192.png").is_file())
        self.assertTrue((public / "pwa-icon-512.png").is_file())
        self.assertTrue((public / "apple-touch-icon.png").is_file())
        sw = (public / "sw.js").read_text(encoding="utf-8")
        self.assertIn("fetch(event.request)", sw)
        self.assertNotIn("caches", sw)
