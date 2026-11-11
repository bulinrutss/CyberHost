"""Testes de estatísticas de sites (visualizações e cliques)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.auth_security import AuthThrottle
from app.models.cloud_storage_order import CloudStorageOrder  # noqa: F401
from app.models.game_server import GameOrder, GameServer  # noqa: F401
from app.models.user import User
from app.models.vps import VpsInstance, VpsOrder  # noqa: F401
from app.models.web_site import WebOrder, WebSite, WebSiteStatus  # noqa: F401
from app.models.web_site_analytics import WebSiteAnalyticsEvent
from app.schemas.web_page import WebPageConfig, WebPageLink
from app.services.web_page_builder import save_page
from app.services.web_site_analytics import (
    collect_stats,
    record_link_click,
    record_page_view,
    resolve_click_redirect,
)


def _request(ua: str = "Mozilla/5.0") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"user-agent", ua.encode())],
        "client": ("203.0.113.10", 12345),
    }
    return Request(scope)


class WebSiteAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                WebSite.__table__,
                WebSiteAnalyticsEvent.__table__,
                AuthThrottle.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            email="u@test.com",
            hashed_password="x",
            phone="+5511999999999",
            name="Test",
        )
        self.db.add(self.user)
        self.db.flush()
        self.data_path = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.data_path, "public"))
        self.site = WebSite(
            user_id=self.user.id,
            site_slug="loja",
            data_path=self.data_path,
            status=WebSiteStatus.RUNNING,
            disk_mb=512,
            ram_mb=256,
            cpu_percent=50,
            port=9101,
        )
        self.db.add(self.site)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.data_path, ignore_errors=True)

    def _save_builder_page(self) -> None:
        config = WebPageConfig(
            template_id="minimal",
            title="Loja",
            subtitle="Bio",
            links=[WebPageLink(id="lnk1", label="Instagram", url="https://instagram.com/x")],
        )
        save_page(self.site, config)

    def test_page_view_and_click_stats(self) -> None:
        self._save_builder_page()
        req = _request()
        self.assertTrue(record_page_view(self.db, req, site_slug="loja", visitor_id="visitor-abc12345"))
        self.db.commit()
        link = WebPageLink(id="lnk1", label="Instagram", url="https://instagram.com/x")
        record_link_click(self.db, req, site=self.site, link=link, visitor_id="visitor-abc12345")
        self.db.commit()
        stats = collect_stats(self.db, self.site, days=30)
        self.assertEqual(stats["page_views"], 1)
        self.assertEqual(stats["link_clicks"], 1)
        self.assertEqual(stats["unique_visitors"], 1)
        self.assertEqual(stats["links"][0]["clicks"], 1)

    def test_redirect_resolves_target(self) -> None:
        self._save_builder_page()
        target = resolve_click_redirect(self.db, _request(), site_slug="loja", link_id="lnk1")
        self.assertEqual(target, "https://instagram.com/x")
        stats = collect_stats(self.db, self.site, days=30)
        self.assertEqual(stats["link_clicks"], 1)

    def test_bot_page_views_ignored(self) -> None:
        self._save_builder_page()
        self.assertFalse(
            record_page_view(
                self.db,
                _request(ua="Googlebot/2.1 (+http://www.google.com/bot.html)"),
                site_slug="loja",
                visitor_id="bot-visitor1",
            )
        )


if __name__ == "__main__":
    unittest.main()
