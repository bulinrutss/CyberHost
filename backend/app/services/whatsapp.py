"""Envio de templates de autenticação pela WhatsApp Cloud API."""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.utils.phone import to_whatsapp_e164

logger = logging.getLogger(__name__)

_UNDELIVERABLE = {131026, 131047}
_PAIR_RATE = {131056}


def verification_required() -> bool:
    settings = get_settings()
    return bool(settings.whatsapp_enabled)


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"


def _graph_error_code(body: object) -> int | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def send_authentication_code(phone: str, code: str) -> None:
    """Entrega o OTP. Não registra o código nem o token."""
    settings = get_settings()
    token = settings.whatsapp_access_token.strip()
    phone_id = settings.whatsapp_phone_number_id.strip()
    if not settings.whatsapp_enabled or not token or not phone_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Confirmação por WhatsApp indisponível",
        )

    destination = to_whatsapp_e164(phone)
    version = settings.whatsapp_graph_version.strip().lstrip("/") or "v22.0"
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    components: list[dict] = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": code}],
        }
    ]
    if settings.whatsapp_template_button:
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": code}],
            }
        )
    payload = {
        "messaging_product": "whatsapp",
        "to": destination,
        "type": "template",
        "template": {
            "name": settings.whatsapp_template_name.strip() or "verification_code",
            "language": {
                "code": settings.whatsapp_template_language.strip() or "pt_BR"
            },
            "components": components,
        },
    }

    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
    except httpx.TimeoutException as exc:
        logger.warning("whatsapp timeout phone=%s", _mask_phone(phone))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível enviar o código. Tente de novo em instantes.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("whatsapp transport error phone=%s", _mask_phone(phone))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível enviar o código. Tente de novo em instantes.",
        ) from exc

    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = None
        code_num = _graph_error_code(body)
        logger.warning(
            "whatsapp send failed phone=%s status=%s code=%s",
            _mask_phone(phone),
            response.status_code,
            code_num or "-",
        )
        if code_num in _UNDELIVERABLE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este número não tem WhatsApp ou não pode receber a mensagem.",
            )
        if code_num in _PAIR_RATE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Aguarde alguns segundos antes de reenviar o código.",
                headers={"Retry-After": "6"},
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível enviar o código. Tente de novo em instantes.",
        )
