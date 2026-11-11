"""Tombstone e retry da exclusão de mensagens Discord do CyberCloud."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.cloud_file import CloudDiscordTombstone, CloudFile, CloudFileChunk
from app.services.cloud_log import TAG_CLOUD, TAG_DISCORD, log_info
from app.services.discord_storage import get_discord_storage

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 20
_MAX_BACKOFF_SECONDS = 3600
_PURGE_BATCH = 25
_purge_lock = threading.Lock()
_purge_running = False


def enqueue_chunk_tombstones(db: Session, user_id: int, node: CloudFile) -> int:
    """Copia IDs Discord antes de apagar o arquivo visível. Não chama a API ainda."""
    chunks = (
        db.query(CloudFileChunk)
        .filter(CloudFileChunk.file_id == node.id)
        .all()
    )
    queued = 0
    now = datetime.utcnow()
    for chunk in chunks:
        if not chunk.discord_message_id or not chunk.discord_channel_id:
            continue
        row = CloudDiscordTombstone(
            user_id=user_id,
            file_id=node.id,
            chunk_index=chunk.chunk_index,
            discord_channel_id=chunk.discord_channel_id,
            discord_message_id=chunk.discord_message_id,
            discord_bot_index=chunk.discord_bot_index,
            next_retry_at=now,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            queued += 1
        except IntegrityError:
            continue
    if queued:
        log_info(
            logger,
            TAG_CLOUD,
            "Tombstone Discord file_id=%s chunks=%s",
            node.id,
            queued,
        )
    return queued


def _backoff_seconds(attempts: int) -> int:
    return min(_MAX_BACKOFF_SECONDS, 15 * (2 ** max(0, min(attempts, 8) - 1)))


def purge_discord_tombstones(db: Session | None = None, *, limit: int = _PURGE_BATCH) -> int:
    """Tenta apagar mensagens tombstoned. Remove a linha só após sucesso/404."""
    owns = db is None
    if owns:
        db = SessionLocal()
    removed = 0
    try:
        now = datetime.utcnow()
        query = (
            db.query(CloudDiscordTombstone)
            .filter(CloudDiscordTombstone.next_retry_at <= now)
            .order_by(CloudDiscordTombstone.id.asc())
            .limit(limit)
        )
        bind = db.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            query = query.with_for_update(skip_locked=True)
        rows = query.all()
        if not rows:
            return 0
        storage = get_discord_storage()
        for row in rows:
            gone = storage.try_delete_message(
                row.discord_channel_id,
                row.discord_message_id,
                row.discord_bot_index or 0,
            )
            if gone:
                db.delete(row)
                removed += 1
                log_info(
                    logger,
                    TAG_DISCORD,
                    "Mensagem Discord apagada file_id=%s chunk=%s",
                    row.file_id,
                    row.chunk_index,
                )
                continue
            row.attempts += 1
            row.last_error = "discord_delete_failed"
            row.next_retry_at = now + timedelta(seconds=_backoff_seconds(row.attempts))
            log_info(
                logger,
                TAG_DISCORD,
                "Retry Discord file_id=%s chunk=%s attempt=%s",
                row.file_id,
                row.chunk_index,
                row.attempts,
            )
        db.commit()
        return removed
    except Exception:
        db.rollback()
        raise
    finally:
        if owns:
            db.close()


def schedule_discord_purge() -> None:
    global _purge_running
    with _purge_lock:
        if _purge_running:
            return
        _purge_running = True

    def _run() -> None:
        global _purge_running
        try:
            purge_discord_tombstones()
        except Exception:
            logger.exception("Falha no purge Discord")
        finally:
            with _purge_lock:
                _purge_running = False

    threading.Thread(target=_run, daemon=True, name="discord-purge").start()


async def discord_purge_loop(interval_seconds: int = PURGE_INTERVAL_SECONDS) -> None:
    while True:
        try:
            removed = await asyncio.to_thread(purge_discord_tombstones)
            if removed:
                logger.info("Discord purge: %s mensagem(ns) removida(s)", removed)
        except Exception:
            logger.exception("Erro no loop de purge Discord")
        await asyncio.sleep(interval_seconds)
