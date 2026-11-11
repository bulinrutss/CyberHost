import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WebOrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WebOrderType(str, enum.Enum):
    NEW = "new"
    RENEWAL = "renewal"


class WebSiteStatus(str, enum.Enum):
    CREATING = "creating"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    DELETED = "deleted"


PAYMENT_RECONCILE_STATUSES = (WebOrderStatus.PENDING_PAYMENT, WebOrderStatus.CANCELLED)


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class WebPlanPreset(Base):
    __tablename__ = "web_plan_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    ram_mb: Mapped[int] = mapped_column(Integer)
    disk_mb: Mapped[int] = mapped_column(Integer)
    cpu_percent: Mapped[int] = mapped_column(Integer)
    php_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    price_cents: Mapped[int] = mapped_column(Integer)
    cloud_bonus_gb: Mapped[int] = mapped_column(Integer, default=0)
    is_popular: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class WebOrder(Base):
    __tablename__ = "web_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_type: Mapped[WebOrderType] = mapped_column(
        Enum(WebOrderType, values_callable=_enum_values, native_enum=False, length=20),
        default=WebOrderType.NEW,
    )
    target_site_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_sites.id"), nullable=True, index=True
    )
    renewal_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preset_id: Mapped[int | None] = mapped_column(ForeignKey("web_plan_presets.id"), nullable=True)
    site_slug: Mapped[str] = mapped_column(String(63))
    domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    ram_mb: Mapped[int] = mapped_column(Integer)
    disk_mb: Mapped[int] = mapped_column(Integer)
    cpu_percent: Mapped[int] = mapped_column(Integer)
    php_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("discount_coupons.id"), nullable=True)
    subtotal_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[WebOrderStatus] = mapped_column(
        Enum(WebOrderStatus, values_callable=_enum_values, native_enum=False, length=20),
        default=WebOrderStatus.PENDING_PAYMENT,
    )
    payment_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payment_external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_checkout_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pix_br_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_qr_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provision_progress: Mapped[int] = mapped_column(Integer, default=0)
    provision_step: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", back_populates="web_orders")
    preset = relationship("WebPlanPreset")
    site = relationship(
        "WebSite",
        back_populates="order",
        uselist=False,
        foreign_keys="WebSite.order_id",
    )
    target_site = relationship("WebSite", foreign_keys=[target_site_id], uselist=False)


class WebSite(Base):
    __tablename__ = "web_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_orders.id"), unique=True, nullable=True
    )
    site_slug: Mapped[str] = mapped_column(String(63), unique=True)
    domain: Mapped[str | None] = mapped_column(String(253), unique=True, nullable=True)
    ram_mb: Mapped[int] = mapped_column(Integer)
    disk_mb: Mapped[int] = mapped_column(Integer)
    cpu_percent: Mapped[int] = mapped_column(Integer)
    php_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    port: Mapped[int] = mapped_column(Integer)
    data_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[WebSiteStatus] = mapped_column(
        Enum(WebSiteStatus, values_callable=_enum_values, native_enum=False, length=20),
        default=WebSiteStatus.CREATING,
    )
    process_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    billing_day: Mapped[int] = mapped_column(Integer, default=1)
    suspended_for_billing: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", back_populates="web_sites")
    order = relationship("WebOrder", back_populates="site", foreign_keys=[order_id])
