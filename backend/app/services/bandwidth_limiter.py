"""Limite global de banda (bytes/s) para transferências do cloud de arquivos."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Iterator

from app.config import get_settings


class TransferLimitExceeded(ValueError):
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"Transfer exceeds {max_bytes} bytes")


class EmptyTransfer(ValueError):
    pass

_lock = threading.Lock()
_tokens: float = 0.0
_last_refill: float = time.monotonic()


def limit_bps() -> float:
    mbps = get_settings().cloud_files_bandwidth_limit_mbps
    if mbps <= 0:
        return 0.0
    # Megabits/s (decimal) → bytes/s
    return mbps * 1_000_000 / 8


def enabled() -> bool:
    return limit_bps() > 0


def acquire(byte_count: int) -> None:
    """Aguarda até poder transferir byte_count bytes dentro do limite global."""
    if byte_count <= 0:
        return

    bps = limit_bps()
    if bps <= 0:
        return

    global _tokens, _last_refill

    while True:
        with _lock:
            now = time.monotonic()
            elapsed = now - _last_refill
            if elapsed > 0:
                _tokens = min(bps, _tokens + elapsed * bps)
                _last_refill = now
            if _tokens >= byte_count:
                _tokens -= byte_count
                return
            deficit = byte_count - _tokens
            wait_seconds = deficit / bps
        time.sleep(min(max(wait_seconds, 0.01), 1.0))


def stream_to_path(
    raw_file,
    dest: Path,
    max_bytes: int,
    chunk_size: int = 65536,
) -> int:
    """Grava o stream em disco em blocos, com teto rígido. Não junta o corpo em RAM."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    written = 0
    try:
        with tmp.open("wb") as out:
            while True:
                block = raw_file.read(chunk_size)
                if not block:
                    break
                written += len(block)
                if written > max_bytes:
                    raise TransferLimitExceeded(max_bytes)
                acquire(len(block))
                out.write(block)
        if written == 0:
            raise EmptyTransfer()
        tmp.replace(dest)
        return written
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def iter_capped(blocks: Iterator[bytes], max_bytes: int) -> Iterator[bytes]:
    """Repassa blocos com teto rígido; não acumula o corpo."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    total = 0
    for block in blocks:
        if not block:
            continue
        total += len(block)
        if total > max_bytes:
            raise TransferLimitExceeded(max_bytes)
        acquire(len(block))
        yield block


def iter_file(path: Path, chunk_size: int = 65536) -> Iterator[bytes]:
    """Stream de arquivo local com limite de banda (resposta ao cliente)."""
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            acquire(len(block))
            yield block
