"""Redirect de browser após checkout CyberCloud — sem consultar pedido nem creditar."""

from app.config import get_settings


def browser_files_url() -> str:
    return f"{get_settings().resolved_frontend_url}/dashboard/files"
