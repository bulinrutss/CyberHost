"""Testes unitários das sessões opacas (access + refresh rotativo)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import DEVICE_COOKIE_NAME, REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME, hash_password
from app.database import Base
from app.models.auth_security import AuthSession
from app.models.user import User
from app.services import auth_sessions


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        secret_key="k" * 40,
        auth_access_minutes=15,
        auth_refresh_hours=12,
        app_environment="development",
    )


def _request(
    *,
    cookies: dict[str, str] | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    header_list = list(headers or [])
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        header_list.append((b"cookie", cookie_header.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": header_list,
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 80),
        }
    )


class AuthSessionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, AuthSession.__table__],
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            phone="11988880001",
            name="Cliente",
            hashed_password=hash_password("correct-horse"),
            is_active=True,
            is_admin=False,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.settings_patch = patch(
            "app.services.auth_sessions.get_settings",
            return_value=_settings(),
        )
        self.auth_settings_patch = patch(
            "app.auth.get_settings",
            return_value=_settings(),
        )
        self.throttle_patch = patch(
            "app.services.auth_throttle.get_settings",
            return_value=_settings(),
        )
        self.settings_patch.start()
        self.auth_settings_patch.start()
        self.throttle_patch.start()

    def tearDown(self) -> None:
        self.throttle_patch.stop()
        self.auth_settings_patch.stop()
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _create(self, device_id: str = "device-aaaaaaaaaaaaaaaaaaaaaaaaaaaa") -> tuple[Request, Response, AuthSession]:
        request = _request(
            cookies={DEVICE_COOKIE_NAME: device_id},
            headers=[(b"user-agent", b"unit-test/1.0")],
        )
        response = Response()
        row = auth_sessions.create_session(self.db, self.user, request, response)
        return request, response, row

    def _cookie_map(self, response: Response) -> dict[str, str]:
        # Starlette stores raw Set-Cookie; pull from response cookies if available.
        out: dict[str, str] = {}
        for key, value in response.headers.raw:
            if key.lower() != b"set-cookie":
                continue
            text = value.decode("latin-1")
            first = text.split(";", 1)[0]
            if "=" not in first:
                continue
            name, val = first.split("=", 1)
            if val and val != '""':
                out[name] = val
        return out

    def test_create_session_persists_hashes_and_sets_cookies(self) -> None:
        _request_obj, response, row = self._create()
        self.assertIsNotNone(row.id)
        self.assertEqual(row.user_id, self.user.id)
        self.assertTrue(row.access_token_hash)
        self.assertTrue(row.refresh_token_hash)
        self.assertIsNone(row.revoked_at)
        cookies = self._cookie_map(response)
        self.assertIn(SESSION_COOKIE_NAME, cookies)
        self.assertIn(REFRESH_COOKIE_NAME, cookies)
        self.assertIn(DEVICE_COOKIE_NAME, cookies)
        access_raw = cookies[SESSION_COOKIE_NAME]
        resolved = auth_sessions.resolve_user_from_access(
            self.db,
            _request(
                cookies={
                    SESSION_COOKIE_NAME: access_raw,
                    DEVICE_COOKIE_NAME: cookies[DEVICE_COOKIE_NAME],
                }
            ),
            access_raw,
        )
        self.assertEqual(resolved.id, self.user.id)

    def test_device_mismatch_rejects_access(self) -> None:
        _req, response, _row = self._create()
        cookies = self._cookie_map(response)
        access_raw = cookies[SESSION_COOKIE_NAME]
        with self.assertRaises(HTTPException) as ctx:
            auth_sessions.resolve_user_from_access(
                self.db,
                _request(
                    cookies={
                        SESSION_COOKIE_NAME: access_raw,
                        DEVICE_COOKIE_NAME: "other-machine-device-id-0123456789ab",
                    }
                ),
                access_raw,
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_refresh_rotation_issues_new_tokens(self) -> None:
        _req, response, row = self._create()
        cookies = self._cookie_map(response)
        refresh_req = _request(
            cookies={
                REFRESH_COOKIE_NAME: cookies[REFRESH_COOKIE_NAME],
                DEVICE_COOKIE_NAME: cookies[DEVICE_COOKIE_NAME],
            }
        )
        new_response = Response()
        user = auth_sessions.rotate_refresh(self.db, refresh_req, new_response)
        self.assertEqual(user.id, self.user.id)
        self.db.refresh(row)
        self.assertIsNotNone(row.revoked_at)
        new_cookies = self._cookie_map(new_response)
        self.assertIn(SESSION_COOKIE_NAME, new_cookies)
        self.assertIn(REFRESH_COOKIE_NAME, new_cookies)
        self.assertNotEqual(cookies[REFRESH_COOKIE_NAME], new_cookies[REFRESH_COOKIE_NAME])
        active = (
            self.db.query(AuthSession)
            .filter(
                AuthSession.user_id == self.user.id,
                AuthSession.revoked_at.is_(None),
            )
            .one()
        )
        self.assertEqual(active.refresh_family, row.refresh_family)

    def test_refresh_reuse_revokes_family(self) -> None:
        _req, response, row = self._create()
        cookies = self._cookie_map(response)
        old_refresh = cookies[REFRESH_COOKIE_NAME]
        device = cookies[DEVICE_COOKIE_NAME]
        first = Response()
        auth_sessions.rotate_refresh(
            self.db,
            _request(cookies={REFRESH_COOKIE_NAME: old_refresh, DEVICE_COOKIE_NAME: device}),
            first,
        )
        with self.assertRaises(HTTPException) as ctx:
            auth_sessions.rotate_refresh(
                self.db,
                _request(cookies={REFRESH_COOKIE_NAME: old_refresh, DEVICE_COOKIE_NAME: device}),
                Response(),
            )
        self.assertEqual(ctx.exception.status_code, 401)
        self.db.expire_all()
        family_rows = (
            self.db.query(AuthSession)
            .filter(AuthSession.refresh_family == row.refresh_family)
            .all()
        )
        self.assertTrue(family_rows)
        self.assertTrue(all(r.revoked_at is not None for r in family_rows))


if __name__ == "__main__":
    unittest.main()
