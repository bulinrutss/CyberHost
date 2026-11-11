"""Saída segura no console Windows (evita UnicodeEncodeError com cp1252)."""

from __future__ import annotations

import logging
import re
import sys


_WEBHOOK_SECRET_PATTERN = re.compile(r"([?&]webhookSecret=)[^&\s\"]+", re.IGNORECASE)


def _redact_webhook_secret(value: object) -> object:
    if not isinstance(value, str):
        return value
    return _WEBHOOK_SECRET_PATTERN.sub(r"\1[REDACTED]", value)


class _SensitiveQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_webhook_secret(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_webhook_secret(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_webhook_secret(value) for key, value in record.args.items()
            }
        return True


_sensitive_query_filter = _SensitiveQueryFilter()


def configure_stdio() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def configure_logging() -> None:
    """Garante que handlers de log não quebrem com caracteres fora do cp1252."""
    configure_stdio()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
        )
        root.addHandler(handler)
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        for handler in log.handlers:
            if not any(isinstance(item, _SensitiveQueryFilter) for item in handler.filters):
                handler.addFilter(_sensitive_query_filter)
            stream = getattr(handler, "stream", None)
            if stream is None:
                continue
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass


def sanitize_for_console(text: str) -> str:
    """Remove/substitui caracteres que o console Windows não consegue exibir."""
    if not text:
        return text
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except LookupError:
        return text.encode("ascii", errors="replace").decode("ascii")


def safe_print(text: str) -> None:
    payload = sanitize_for_console(text)
    try:
        # stderr aparece de forma confiável no terminal do uvicorn (Windows)
        print(payload, file=sys.stderr, flush=True)
    except UnicodeEncodeError:
        sys.stderr.buffer.write(payload.encode("utf-8", errors="replace") + b"\n")
        sys.stderr.flush()


def safe_log_info(logger: logging.Logger, msg: str, *args) -> None:
    try:
        logger.info(msg, *args)
    except UnicodeEncodeError:
        safe_args = tuple(
            sanitize_for_console(arg) if isinstance(arg, str) else arg for arg in args
        )
        try:
            logger.info(msg, *safe_args)
        except UnicodeEncodeError:
            logger.info("%s (conteúdo omitido — caracteres inválidos no console)", msg.split("%")[0])
