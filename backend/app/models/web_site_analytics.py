from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WebSiteAnalyticsEvent(Base):
    __tablename__ = "web_site_analytics_events"
    __table_args__ = (
        Index("ix_web_analytics_site_created", "site_id", "created_at"),
        Index("ix_web_analytics_site_type_created", "site_id", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("web_sites.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    link_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    link_label: Mapped[str] = mapped_column(String(80), default="")
    visitor_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
