"""Envio de e-mail transacional via SMTP (OTP e lembretes)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings
from app.services import email_templates

logger = logging.getLogger(__name__)

_LOGO_CID = "cyberhost-logo"


def verification_required() -> bool:
    return bool(get_settings().email_otp_enabled)


def smtp_configured(settings=None) -> bool:
    cfg = settings or get_settings()
    return bool(str(getattr(cfg, "smtp_host", "") or "").strip() and str(getattr(cfg, "smtp_from", "") or "").strip())


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    prefix = local[:1] if local else "*"
    return f"{prefix}***@{domain}"


def panel_url(path: str) -> str:
    """URL do painel (inclui /cyberhost em produção)."""
    path = "/" + str(path or "").lstrip("/")
    base = get_settings().resolved_frontend_url.rstrip("/")
    host = base.lower()
    if "localhost" in host or "127.0.0.1" in host or base.endswith("/cyberhost"):
        return f"{base}{path}"
    return f"{base}/cyberhost{path}"


def logo_file_path() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "frontend" / "public" / "logo3.png",
        Path("/opt/host/frontend/public/logo3.png"),
        here.parents[3] / "frontend" / "public" / "logo2.png",
        Path("/opt/host/frontend/public/logo2.png"),
        Path("/opt/host/frontend/public/cyberhost/logo2.png"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def logo_src(*, inline: bool) -> str:
    if inline:
        return f"cid:{_LOGO_CID}"
    try:
        return panel_url("/logo2.png")
    except Exception:
        return "https://ruts.dev/cyberhost/logo2.png"


def load_logo_bytes() -> bytes | None:
    path = logo_file_path()
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data or len(data) > 80_000:
        return None
    return data


def build_message(
    *,
    to_email: str,
    subject: str,
    text: str,
    html: str | None = None,
    inline_logo: bytes | None = None,
) -> EmailMessage:
    settings = get_settings()
    sender = settings.smtp_from.strip()
    from_name = settings.smtp_from_name.strip() or "CyberHost"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{sender}>"
    message["To"] = to_email
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
        if inline_logo:
            html_part = None
            for part in message.iter_parts():
                if part.get_content_subtype() == "html":
                    html_part = part
                    break
            if html_part is not None:
                html_part.add_related(
                    inline_logo,
                    maintype="image",
                    subtype="png",
                    cid=_LOGO_CID,
                )
    return message


def send_email(
    *,
    to_email: str,
    subject: str,
    text: str,
    html: str | None = None,
    inline_logo: bool = True,
) -> None:
    settings = get_settings()
    host = settings.smtp_host.strip()
    sender = settings.smtp_from.strip()
    if not host or not sender:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Envio de e-mail indisponível",
        )

    logo = load_logo_bytes() if inline_logo else None
    message = build_message(
        to_email=to_email,
        subject=subject,
        text=text,
        html=html,
        inline_logo=logo,
    )
    try:
        if settings.smtp_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, int(settings.smtp_port), context=context, timeout=20) as smtp:
                _login_and_send(smtp, settings, sender, to_email, message)
        else:
            with smtplib.SMTP(host, int(settings.smtp_port), timeout=20) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                _login_and_send(smtp, settings, sender, to_email, message)
    except HTTPException:
        raise
    except (smtplib.SMTPException, OSError, TimeoutError):
        logger.warning("smtp send failed to=%s", _mask_email(to_email))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível enviar o e-mail. Tente de novo em instantes.",
        ) from None


def send_otp_email(to_email: str, code: str, ttl_seconds: int) -> None:
    settings = get_settings()
    if not settings.email_otp_enabled or not smtp_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Confirmação por e-mail indisponível",
        )
    minutes = max(1, ttl_seconds // 60)
    logo = load_logo_bytes()
    subject, text, html = email_templates.otp_content(
        code=code,
        minutes=minutes,
        logo_src=logo_src(inline=bool(logo)),
    )
    send_email(to_email=to_email, subject=subject, text=text, html=html, inline_logo=True)


def _login_and_send(smtp: smtplib.SMTP, settings, sender: str, to_email: str, message: EmailMessage) -> None:
    user = settings.smtp_username.strip()
    password = settings.smtp_password
    if user:
        smtp.login(user, password)
    smtp.send_message(message, from_addr=sender, to_addrs=[to_email])
