import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"


PAYMENT_RECONCILE_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED)


class VpsStatus(str, enum.Enum):
    CREATING = "creating"
    CONFIGURING = "configuring"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DELETED = "deleted"


class OrderType(str, enum.Enum):
    NEW = "new"
    UPGRADE = "upgrade"
    RENEWAL = "renewal"
    ADMIN = "admin"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class VpsPlan(Base):
    __tablename__ = "vps_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), default="vps")
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    min_vcpu: Mapped[int] = mapped_column(Integer, default=1)
    max_vcpu: Mapped[int] = mapped_column(Integer, default=8)
    min_ram_mb: Mapped[int] = mapped_column(Integer, default=1024)
    max_ram_mb: Mapped[int] = mapped_column(Integer, default=8192)
    network_mbps: Mapped[int] = mapped_column(Integer, default=100)
    default_disk_gb: Mapped[int] = mapped_column(Integer, default=30)
    max_disk_gb: Mapped[int] = mapped_column(Integer, default=500)
    monthly_base_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_per_vcpu_cents: Mapped[int] = mapped_column(Integer, default=1000)
    price_per_gb_ram_cents: Mapped[int] = mapped_column(Integer, default=1000)
    price_per_gb_disk_cents: Mapped[int] = mapped_column(Integer, default=150)
    is_active: Mapped[bool] = mapped_column(default=True)
    presets = relationship("VpsPlanPreset", back_populates="plan")


class VpsPlanPreset(Base):
    __tablename__ = "vps_plan_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("vps_plans.id"))
    slug: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    vcpu: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    disk_gb: Mapped[int] = mapped_column(Integer)
    cloud_bonus_gb: Mapped[int] = mapped_column(Integer, default=0)
    price_cents: Mapped[int] = mapped_column(Integer)
    is_popular: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    plan = relationship("VpsPlan", back_populates="presets")


class VpsOrder(Base):
    __tablename__ = "vps_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("vps_plans.id"))
    vcpu: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    hostname: Mapped[str] = mapped_column(String(63))
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, values_callable=_enum_values),
        default=OrderType.NEW,
    )
    target_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("vps_instances.id"), nullable=True
    )
    disk_gb: Mapped[int] = mapped_column(Integer, default=30)
    os_template: Mapped[str] = mapped_column(String(20), default="sv2016")
    renewal_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upgrade_monthly_delta_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("discount_coupons.id"), nullable=True)
    subtotal_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING_PAYMENT)
    total_cents: Mapped[int] = mapped_column(Integer)
    payment_provider: Mapped[str] = mapped_column(String(40), default="abacatepay")
    payment_external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_br_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_qr_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provision_progress: Mapped[int] = mapped_column(Integer, default=0)
    provision_step: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    plan = relationship("VpsPlan")
    instance = relationship(
        "VpsInstance",
        back_populates="order",
        uselist=False,
        foreign_keys="VpsInstance.order_id",
    )
    target_instance = relationship(
        "VpsInstance",
        foreign_keys=[target_instance_id],
        uselist=False,
    )


class VpsInstance(Base):
    __tablename__ = "vps_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("vps_orders.id"), unique=True, nullable=True
    )
    vm_name: Mapped[str] = mapped_column(String(80), unique=True)
    vm_moid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("vps_plans.id"), nullable=True)
    vcpu: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    disk_gb: Mapped[int] = mapped_column(Integer, default=30)
    os_template: Mapped[str] = mapped_column(String(20), default="sv2016")
    network_mbps: Mapped[int] = mapped_column(Integer, default=300)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    windows_admin_password: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[VpsStatus] = mapped_column(Enum(VpsStatus), default=VpsStatus.CREATING)
    esxi_host: Mapped[str] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    billing_day: Mapped[int] = mapped_column(Integer, default=1)
    suspended_for_billing: Mapped[bool] = mapped_column(default=False)
    admin_pending_charge_cents: Mapped[int] = mapped_column(Integer, default=0)
    custom_monthly_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="vps_instances")
    order = relationship(
        "VpsOrder",
        back_populates="instance",
        foreign_keys=[order_id],
    )
    plan = relationship("VpsPlan")
    connection_domains = relationship(
        "VpsConnectionDomain",
        back_populates="instance",
        cascade="all, delete-orphan",
    )
