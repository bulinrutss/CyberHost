#!/usr/bin/env python3
"""Processo stub para dev/teste quando binários reais não estão configurados."""

from __future__ import annotations

import argparse
import socket
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", default="server")
    parser.add_argument("--slots", type=int, default=50)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", args.port))
    except OSError as exc:
        print(f"[stub] Falha ao abrir porta {args.port}: {exc}", flush=True)
        return 1

    print(
        f"[stub] {args.game.upper()} '{args.name}' rodando na porta {args.port} "
        f"({args.slots} slots) — modo desenvolvimento",
        flush=True,
    )
    sock.settimeout(1.0)
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            if data:
                print(f"[stub] pacote de {addr[0]}:{addr[1]} ({len(data)} bytes)", flush=True)
        except socket.timeout:
            pass
        except KeyboardInterrupt:
            break
    sock.close()
    print("[stub] encerrado", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
