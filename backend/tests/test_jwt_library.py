from datetime import datetime, timezone
import unittest

import jwt
from jwt.exceptions import InvalidTokenError

from app.auth import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, create_access_token


class JwtLibraryTests(unittest.TestCase):
    def test_access_token_uses_hs256_and_round_trips(self) -> None:
        from app.config import get_settings

        token = create_access_token(42)
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        self.assertEqual(payload["sub"], "42")
        header = jwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "HS256")
        remaining = payload["exp"] - datetime.now(timezone.utc).timestamp()
        window = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        self.assertLess(remaining, window + 60)
        self.assertGreater(remaining, window - 120)
        self.assertLess(window, 9 * 3600)

    def test_none_algorithm_is_rejected(self) -> None:
        from app.config import get_settings

        header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"
        payload = "eyJzdWIiOiI0MiJ9"
        forged = f"{header}.{payload}."
        with self.assertRaises(InvalidTokenError):
            jwt.decode(forged, get_settings().secret_key, algorithms=[ALGORITHM])


if __name__ == "__main__":
    unittest.main()
