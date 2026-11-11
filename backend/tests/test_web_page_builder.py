"""Testes do criador de página estilo Linktree."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas.web_page import WebPageConfig, WebPageLink
from app.services.web_page_builder import load_config, render_html, save_page


class WebPageBuilderTests(unittest.TestCase):
    def _site(self, tmp: str, *, slug: str = "loja", domain: str | None = None) -> SimpleNamespace:
        root = Path(tmp)
        data = root / "2" / "1"
        (data / "public").mkdir(parents=True)
        return SimpleNamespace(
            id=1,
            user_id=2,
            site_slug=slug,
            domain=domain,
            data_path=str(data),
            php_enabled=False,
        )

    def test_save_and_render_escapes_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp)
            config = WebPageConfig(
                template_id="minimal",
                title='<script>alert(1)</script>',
                subtitle="Bio & teste",
                links=[
                    WebPageLink(id="a", label="Link", url="https://example.com"),
                ],
            )
            save_page(site, config)
            html = (Path(site.data_path) / "public" / "index.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>alert", html)
            loaded = load_config(site)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.title, '<script>alert(1)</script>')

    def test_render_uses_root_with_platform_subdomain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp)
            config = WebPageConfig(
                template_id="neon",
                title="Nome",
                subtitle="",
                links=[],
            )
            with patch(
                "app.services.web_page_builder.platform_subdomain_for_site",
                return_value="loja.ruts.dev",
            ):
                html = render_html(site, config)
            self.assertIn('base href="/"', html)
            self.assertNotIn("/s/loja/", html)

    def test_render_uses_path_prefix_without_platform_subdomain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp)
            config = WebPageConfig(
                template_id="neon",
                title="Nome",
                subtitle="",
                links=[],
            )
            with patch(
                "app.services.web_page_builder.platform_subdomain_for_site",
                return_value=None,
            ):
                html = render_html(site, config)
            self.assertIn('base href="/s/loja/"', html)

    def test_render_root_base_with_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp, domain="loja.com")
            config = WebPageConfig(template_id="sunset", title="Loja", subtitle="Oi", links=[])
            html = render_html(site, config)
            self.assertIn('base href="/"', html)


    def test_render_includes_link_icon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp)
            config = WebPageConfig(
                template_id="minimal",
                title="Nome",
                subtitle="",
                links=[
                    WebPageLink(id="a", label="Instagram", url="https://instagram.com/x", icon="instagram"),
                ],
            )
            html = render_html(site, config)
            self.assertIn('class="link minimal with-icon"', html)
            self.assertIn('class="link-icon"', html)
            self.assertIn("Instagram", html)

    def test_render_includes_tracking_and_redirect_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(tmp)
            config = WebPageConfig(
                template_id="minimal",
                title="Nome",
                subtitle="",
                links=[
                    WebPageLink(id="lnk1", label="Site", url="https://example.com"),
                ],
            )
            save_page(site, config)
            html = (Path(site.data_path) / "public" / "index.html").read_text(encoding="utf-8")
            self.assertIn("/public/pv/", html)
            self.assertIn("/r/loja/lnk1", html)


if __name__ == "__main__":
    unittest.main()
