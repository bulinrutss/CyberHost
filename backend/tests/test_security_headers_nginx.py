import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SecurityHeadersNginxTests(unittest.TestCase):
    def test_origin_includes_security_header_snippet(self) -> None:
        conf = (ROOT / "deploy/nginx/ruts.dev.conf").read_text(encoding="utf-8")
        self.assertIn("include /etc/nginx/snippets/security-headers.conf;", conf)
        self.assertIn("proxy_pass http://127.0.0.1:8810", conf)
        self.assertIn("proxy_pass http://127.0.0.1:3000", conf)
        self.assertIn("proxy_set_header Upgrade $ws_upgrade_header;", conf)
        self.assertIn("proxy_set_header Connection $ws_connection_header;", conf)

    def test_websocket_upgrade_maps_restore_stripped_headers(self) -> None:
        snippet = (ROOT / "deploy/nginx/websocket-upgrade.conf").read_text(encoding="utf-8")
        self.assertIn("map $http_sec_websocket_key $ws_upgrade_header", snippet)
        self.assertIn("map $http_sec_websocket_key $ws_connection_header", snippet)
        self.assertIn("default websocket;", snippet)
        self.assertIn("default upgrade;", snippet)

    def test_snippet_has_required_headers(self) -> None:
        snippet = (ROOT / "deploy/nginx/security-headers.conf").read_text(encoding="utf-8")
        for needle in (
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "nosniff",
            "Referrer-Policy",
            "X-Frame-Options",
            "Content-Security-Policy",
            "frame-ancestors 'none'",
        ):
            self.assertIn(needle, snippet)

    def test_systemd_binds_loopback_only(self) -> None:
        backend = (ROOT / "deploy/systemd/cyberhost-backend.service").read_text(encoding="utf-8")
        frontend = (ROOT / "deploy/systemd/cyberhost-frontend.service").read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1 --port 8810", backend)
        self.assertNotIn("0.0.0.0", backend)
        self.assertIn("-H 127.0.0.1 -p 3000", frontend)
        self.assertNotIn("0.0.0.0", frontend)
