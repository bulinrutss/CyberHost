"""Logs legíveis no console para cloud de arquivos / Discord."""

from __future__ import annotations

import logging
import traceback

from app.console_io import safe_print

TAG_CLOUD = "CloudFiles"
TAG_DISCORD = "Discord"


def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def _format_message(message: str, *args) -> str:
    if not args:
        return message
    try:
        return message % args
    except (TypeError, ValueError):
        return f"{message} {' '.join(str(a) for a in args)}"


def _emit(tag: str, level: str, message: str, *args) -> None:
    text = _format_message(message, *args)
    line = f"[{tag}] {level} {text}"
    safe_print(line)
    # uvicorn sempre mostra o logger uvicorn.error no terminal
    logging.getLogger("uvicorn.error").info(line)


def log_info(logger: logging.Logger, tag: str, message: str, *args) -> None:
    """Imprime no console (sempre visível, independente do uvicorn)."""
    _emit(tag, "INFO", message, *args)


def log_exception(logger: logging.Logger, tag: str, message: str, *args) -> None:
    _emit(tag, "ERROR", message, *args)
    safe_print(traceback.format_exc())


def log_progress(
    logger: logging.Logger,
    tag: str,
    action: str,
    current: int,
    total: int,
    **extra: object,
) -> None:
    pct = (current / total * 100) if total else 0.0
    suffix = " ".join(f"{k}={v}" for k, v in extra.items())
    msg = f"{action} {current}/{total} ({pct:.0f}%)"
    if suffix:
        msg = f"{msg} | {suffix}"
    log_info(logger, tag, msg)