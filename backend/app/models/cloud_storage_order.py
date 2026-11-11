import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CloudStorageOrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"


PAYMENT_RECONCILE_STATUSES = (
    CloudStorageOrderStatus.PENDING_PAYMENT,
    CloudStorageOrderStatus.CANCELLED,
)


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class CloudStorageOrder(Base):
    __tablename__ = "cloud_storage_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    extra_gb: Mapped[int] = mapped_column(Integer, default=0)
    renewal_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[CloudStorageOrderStatus] = mapped_column(
        Enum(CloudStorageOrderStatus, values_callable=_enum_values),
        default=CloudStorageOrderStatus.PENDING_PAYMENT,
    )
    payment_provider: Mapped[str] = mapped_column(String(40), default="abacatepay")
    payment_external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_br_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_qr_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", back_populates="cloud_storage_orders")
