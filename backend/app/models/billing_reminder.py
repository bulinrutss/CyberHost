from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillingReminder(Base):
    """Lembrete de vencimento já enviado (um por serviço + data de vencimento + offset)."""

    __tablename__ = "billing_reminders"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "resource_id",
            "due_on",
            "offset_days",
            name="uq_billing_reminder_send",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    resource_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    offset_days: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
