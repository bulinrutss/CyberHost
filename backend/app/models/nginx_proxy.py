"""Rotas de proxy nginx criadas manualmente pelo administrador."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NginxProxyRoute(Base):
    __tablename__ = "nginx_proxy_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="reverse_proxy")
    upstream_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    include_www: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
