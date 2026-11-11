import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GameType(str, enum.Enum):
    SAMP = "samp"
    MTA = "mta"
    MINECRAFT = "minecraft"
    FIVEM = "fivem"


class GameOrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"


PAYMENT_RECONCILE_STATUSES = (
    GameOrderStatus.PENDING_PAYMENT,
    GameOrderStatus.CANCELLED,
)


class GameServerStatus(str, enum.Enum):
    CREATING = "creating"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    DELETED = "deleted"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class GameHost(Base):
    __tablename__ = "game_hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    public_ip: Mapped[str] = mapped_column(String(45), default="127.0.0.1")
    data_path: Mapped[str] = mapped_column(String(512), default="./data/game_servers")
    port_range_start: Mapped[int] = mapped_column(Integer, default=27000)
    port_range_end: Mapped[int] = mapped_column(Integer, default=27999)
    max_servers: Mapped[int] = mapped_column(Integer, default=50)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    servers = relationship("GameServer", back_populates="host")


class GamePlanPreset(Base):
    __tablename__ = "game_plan_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_type: Mapped[GameType] = mapped_column(
        Enum(GameType, values_callable=_enum_values, native_enum=False, length=20)
    )
    slug: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    slots: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer)
    is_popular: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class GameOrder(Base):
    __tablename__ = "game_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game_type: Mapped[GameType] = mapped_column(
        Enum(GameType, values_callable=_enum_values, native_enum=False, length=20)
    )
    preset_id: Mapped[int | None] = mapped_column(ForeignKey("game_plan_presets.id"), nullable=True)
    slots: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    server_name: Mapped[str] = mapped_column(String(63))
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[GameOrderStatus] = mapped_column(
        Enum(GameOrderStatus, values_callable=_enum_values, native_enum=False, length=20),
        default=GameOrderStatus.PENDING_PAYMENT,
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

    user = relationship("User", back_populates="game_orders")
    preset = relationship("GamePlanPreset")
    server = relationship("GameServer", back_populates="order", uselist=False)


class GameServer(Base):
    __tablename__ = "game_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_orders.id"), unique=True, nullable=True
    )
    host_id: Mapped[int] = mapped_column(ForeignKey("game_hosts.id"))
    game_type: Mapped[GameType] = mapped_column(
        Enum(GameType, values_callable=_enum_values, native_enum=False, length=20)
    )
    server_name: Mapped[str] = mapped_column(String(63))
    slots: Mapped[int] = mapped_column(Integer)
    ram_mb: Mapped[int] = mapped_column(Integer)
    port: Mapped[int] = mapped_column(Integer)
    query_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[GameServerStatus] = mapped_column(
        Enum(GameServerStatus, values_callable=_enum_values, native_enum=False, length=20),
        default=GameServerStatus.CREATING,
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

    user = relationship("User", back_populates="game_servers")
    order = relationship("GameOrder", back_populates="server")
    host = relationship("GameHost", back_populates="servers")
