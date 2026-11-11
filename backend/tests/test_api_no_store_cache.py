import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api_cache_headers import api_no_store_cache


class ApiNoStoreCacheTests(unittest.TestCase):
    def test_api_responses_forbid_shared_caches(self) -> None:
        app = FastAPI()
        app.middleware("http")(api_no_store_cache)

        @app.get("/api/auth/me")
        def me():
            return {"id": 1, "name": "Test"}

        @app.get("/healthz")
        def health():
            return {"ok": True}

        client = TestClient(app)
        api = client.get("/api/auth/me")
        self.assertEqual(api.status_code, 200)
        self.assertIn("no-store", api.headers.get("cache-control", "").lower())
        self.assertIn("private", api.headers.get("cache-control", "").lower())
        self.assertEqual(api.headers.get("cdn-cache-control"), "no-store")
        self.assertIn("Cookie", api.headers.get("vary", ""))
        self.assertIn("Authorization", api.headers.get("vary", ""))

        other = client.get("/healthz")
        self.assertEqual(other.status_code, 200)
        self.assertNotIn("no-store", (other.headers.get("cache-control") or "").lower())


if __name__ == "__main__":
    unittest.main()
