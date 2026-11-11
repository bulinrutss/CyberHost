from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cloud_extra_quota_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    admin_pending_cloud_charge_cents: Mapped[int] = mapped_column(Integer, default=0)
    cloud_contracted_gb: Mapped[int] = mapped_column(Integer, default=0)
    cloud_paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cloud_billing_day: Mapped[int] = mapped_column(Integer, default=1)
    cloud_monthly_cents: Mapped[int] = mapped_column(Integer, default=0)
    cloud_suspended_for_billing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    orders = relationship("VpsOrder", back_populates="user")
    vps_instances = relationship("VpsInstance", back_populates="user")
    cloud_storage_orders = relationship("CloudStorageOrder", back_populates="user")
    game_orders = relationship("GameOrder", back_populates="user")
    game_servers = relationship("GameServer", back_populates="user")
    web_orders = relationship("WebOrder", back_populates="user")
    web_sites = relationship("WebSite", back_populates="user")
