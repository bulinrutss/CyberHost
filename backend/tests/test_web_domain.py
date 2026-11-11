import unittest

from fastapi import HTTPException

from app.services.web_domain import normalize_domain


class WebDomainTests(unittest.TestCase):
    def test_strips_scheme_www_and_path(self) -> None:
        self.assertEqual(normalize_domain("HTTPS://WWW.Loja.Exemplo.com.br/path"), "loja.exemplo.com.br")

    def test_rejects_localhost_and_bare_label(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            normalize_domain("localhost")
        self.assertEqual(raised.exception.status_code, 400)
        with self.assertRaises(HTTPException):
            normalize_domain("site")

    def test_rejects_injection(self) -> None:
        for raw in (
            "loja.com; server_name evil.com",
            "loja.com\nserver_name evil.com",
            "127.0.0.1",
            "../etc",
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(HTTPException) as raised:
                    normalize_domain(raw)
                self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
