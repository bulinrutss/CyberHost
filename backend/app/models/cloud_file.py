from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CloudFile(Base):
    __tablename__ = "cloud_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("cloud_files.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_folder: Mapped[bool] = mapped_column(default=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local")
    upload_status: Mapped[str] = mapped_column(String(32), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    chunks = relationship("CloudFileChunk", back_populates="file", cascade="all, delete-orphan")


class CloudFileChunk(Base):
    """Fragmento (até limite Discord − 1 KB) — no Discord cada chunk vira anexo em mensagem."""

    __tablename__ = "cloud_file_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("cloud_files.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    discord_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discord_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discord_attachment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discord_attachment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discord_url_cached_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discord_bot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    file = relationship("CloudFile", back_populates="chunks")


class CloudDiscordTombstone(Base):
    """IDs Discord preservados até a mensagem ser apagada de fato."""

    __tablename__ = "cloud_discord_tombstones"
    __table_args__ = (
        UniqueConstraint(
            "discord_channel_id",
            "discord_message_id",
            name="uq_cloud_discord_tombstone_message",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    file_id: Mapped[int] = mapped_column(Integer, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    discord_channel_id: Mapped[str] = mapped_column(String(64))
    discord_message_id: Mapped[str] = mapped_column(String(64))
    discord_bot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
