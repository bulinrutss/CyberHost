from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_created", "created_at"),
        Index("ix_analytics_name_created", "name", "created_at"),
        Index("ix_analytics_path_created", "path", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), index=True)
    path: Mapped[str] = mapped_column(String(200), default="/")
    label: Mapped[str] = mapped_column(String(80), default="")
    target: Mapped[str] = mapped_column(String(80), default="")
    href: Mapped[str] = mapped_column(String(200), default="")
    visitor_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    referrer: Mapped[str] = mapped_column(String(120), default="")
    language: Mapped[str] = mapped_column(String(16), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    ua: Mapped[str] = mapped_column(String(160), default="")
    ua_browser: Mapped[str] = mapped_column(String(32), default="")
    ua_os: Mapped[str] = mapped_column(String(32), default="")
    viewport_w: Mapped[int] = mapped_column(Integer, default=0)
    viewport_h: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    scroll_pct: Mapped[int] = mapped_column(Integer, default=0)
    ip_hash: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
