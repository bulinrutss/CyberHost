"""Envio Web Push (VAPID). Não registra nem imprime a chave privada."""

from __future__ import annotations

import json
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


def configured() -> bool:
    return get_settings().web_push_configured


def public_key() -> str | None:
    settings = get_settings()
    if not settings.web_push_configured:
        return None
    key = settings.vapid_public_key.strip()
    return key or None


def send(endpoint: str, p256dh: str, auth: str, payload: dict) -> bool:
    """Envia um aviso. False só quando o endpoint está morto (404/410)."""
    from pywebpush import WebPushException, webpush

    settings = get_settings()
    if not settings.web_push_configured:
        return True
    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_pem,
            vapid_claims={"sub": settings.vapid_subject.strip() or "mailto:cyberhost@ruts.dev"},
        )
        return True
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            return False
        logger.warning("Falha ao enviar web push (status=%s)", status_code)
        return True
    except Exception:
        logger.exception("Falha ao enviar web push")
        return True
