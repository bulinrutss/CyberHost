#!/usr/bin/env python3
"""HTTP estático preso em 127.0.0.1 — um processo por site."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys_stdout = __import__("sys").stderr
        sys_stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        super().end_headers()

    def list_directory(self, path: str):  # noqa: ARG002
        self.send_error(403, "Forbidden")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="web_site_server")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    if args.bind not in {"127.0.0.1", "localhost"}:
        raise SystemExit("bind deve ser 127.0.0.1")
    if not (1 <= args.port <= 65535):
        raise SystemExit("porta inválida")
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise SystemExit("root inexistente")
    os.chdir(root)
    handler = partial(_Handler, directory=str(root))
    httpd = ThreadingHTTPServer((args.bind, args.port), handler)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
