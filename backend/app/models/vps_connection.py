"""Domínio personalizado apontando para uma porta pública da VPS."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VpsConnectionDomain(Base):
    __tablename__ = "vps_connection_domains"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_vps_connection_domains_domain"),
        UniqueConstraint(
            "vps_instance_id",
            "public_port",
            name="uq_vps_connection_domains_instance_port",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vps_instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vps_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    public_port: Mapped[int] = mapped_column(Integer, nullable=False)
    internal_port: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    instance = relationship("VpsInstance", back_populates="connection_domains")
