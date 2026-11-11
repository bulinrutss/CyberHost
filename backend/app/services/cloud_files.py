import io
import logging
import math
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.cloud_file import CloudFile, CloudFileChunk
from app.models.user import User
from app.services import bandwidth_limiter
from app.services.cloud_log import TAG_CLOUD, fmt_bytes, log_exception, log_info, log_progress
from app.services.cloud_discord_purge import enqueue_chunk_tombstones, schedule_discord_purge
from app.services.discord_storage import get_discord_storage
from app.services.game_sandbox import is_under_root

logger = logging.getLogger(__name__)

def _settings():
    return get_settings()


def chunk_size_bytes() -> int:
    return _settings().cloud_files_chunk_size_bytes


def max_upload_bytes() -> int:
    return _settings().cloud_files_max_upload_bytes


def max_concurrent_uploads() -> int:
    return max(1, int(_settings().cloud_files_max_concurrent_uploads or 5))


def expected_chunk_size(
    size_bytes: int,
    chunk_count: int,
    chunk_index: int,
    chunk_size: int,
) -> int:
    """Tamanho máximo do fragmento alinhado à reserva declarada no start."""
    if size_bytes <= 0 or chunk_count <= 0 or chunk_size <= 0:
        return 0
    if chunk_index < 0 or chunk_index >= chunk_count:
        return 0
    if chunk_index < chunk_count - 1:
        return chunk_size
    remainder = size_bytes - chunk_size * (chunk_count - 1)
    return max(0, remainder)


def assert_upload_quota(used: int, incoming: int, limit: int) -> None:
    if incoming <= 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    if used + incoming > limit:
        raise HTTPException(status_code=400, detail="Cota de armazenamento excedida")


def assert_upload_concurrency(active: int, max_allowed: int) -> None:
    if active >= max_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {max_allowed} uploads simultâneos atingido",
        )


@dataclass
class DownloadResult:
    record: CloudFile
    path: Path


def _storage_root() -> Path:
    root = Path(_settings().cloud_files_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _user_dir(user_id: int) -> Path:
    path = _storage_root() / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_dir(user_id: int, file_id: int) -> Path:
    path = _user_dir(user_id) / str(file_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chunk_path(user_id: int, file_id: int, chunk_index: int) -> Path:
    return _file_dir(user_id, file_id) / f"chunk_{chunk_index:06d}"


def _assembled_path(user_id: int, file_id: int) -> Path:
    return _file_dir(user_id, file_id) / "data"


def _uses_discord(record: CloudFile | None = None) -> bool:
    if record is not None:
        return record.storage_backend == "discord"
    return _settings().cloud_files_storage_backend.strip().lower() == "discord"


def _active_backend() -> str:
    return "discord" if _uses_discord() else "local"


def _sanitize_name(name: str) -> str:
    cleaned = name.strip().replace("/", "").replace("\\", "").replace("\0", "")
    if not cleaned or cleaned in (".", ".."):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    return cleaned


def _resolve_parent(db: Session, user: User, parent_id: int | None) -> CloudFile | None:
    if parent_id is None:
        return None
    folder = (
        db.query(CloudFile)
        .filter(
            CloudFile.id == parent_id,
            CloudFile.user_id == user.id,
            CloudFile.is_folder.is_(True),
        )
        .first()
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    return folder


def _filter_by_parent(query, parent_id: int | None):
    if parent_id is None:
        return query.filter(CloudFile.parent_id.is_(None))
    return query.filter(CloudFile.parent_id == parent_id)


def _files_with_name(
    db: Session,
    user_id: int,
    parent_id: int | None,
    name: str,
    *,
    folders: bool | None = None,
) -> list[CloudFile]:
    query = db.query(CloudFile).filter(CloudFile.user_id == user_id, CloudFile.name == name)
    query = _filter_by_parent(query, parent_id)
    if folders is True:
        query = query.filter(CloudFile.is_folder.is_(True))
    elif folders is False:
        query = query.filter(CloudFile.is_folder.is_(False))
    return query.all()


def _duplicate_name(db: Session, user_id: int, parent_id: int | None, name: str) -> bool:
    return bool(_files_with_name(db, user_id, parent_id, name))


def _split_base_ext(name: str) -> tuple[str, str]:
    dot = name.rfind(".")
    if dot <= 0:
        return name, ""
    return name[:dot], name[dot:]


def _ready_name_taken(db: Session, user_id: int, parent_id: int | None, name: str) -> bool:
    matches = _files_with_name(db, user_id, parent_id, name, folders=False)
    return any(m.upload_status == "ready" for m in matches)


def _unique_upload_name(db: Session, user_id: int, parent_id: int | None, name: str) -> str:
    if not _ready_name_taken(db, user_id, parent_id, name):
        return name
    base, ext = _split_base_ext(name)
    for n in range(1, 10_000):
        candidate = f"{base} ({n}){ext}"
        if not _ready_name_taken(db, user_id, parent_id, candidate):
            return candidate
    raise HTTPException(status_code=400, detail="Não foi possível gerar um nome único para o arquivo")


def used_bytes(db: Session, user_id: int, exclude_file_id: int | None = None) -> int:
    """Bytes contabilizados na cota: arquivos prontos + reservas de upload incompleto."""
    query = db.query(CloudFile.size_bytes).filter(
        CloudFile.user_id == user_id,
        CloudFile.is_folder.is_(False),
        CloudFile.upload_status.in_(("ready", "uploading")),
    )
    if exclude_file_id is not None:
        query = query.filter(CloudFile.id != exclude_file_id)
    return sum(int(row[0] or 0) for row in query.all())


def reserved_bytes(db: Session, user_id: int, exclude_file_id: int | None = None) -> int:
    query = db.query(CloudFile.size_bytes).filter(
        CloudFile.user_id == user_id,
        CloudFile.is_folder.is_(False),
        CloudFile.upload_status == "uploading",
    )
    if exclude_file_id is not None:
        query = query.filter(CloudFile.id != exclude_file_id)
    return sum(int(row[0] or 0) for row in query.all())


def uploading_count(db: Session, user_id: int, exclude_file_id: int | None = None) -> int:
    query = db.query(CloudFile).filter(
        CloudFile.user_id == user_id,
        CloudFile.is_folder.is_(False),
        CloudFile.upload_status == "uploading",
    )
    if exclude_file_id is not None:
        query = query.filter(CloudFile.id != exclude_file_id)
    return int(query.count() or 0)


def _lock_user(db: Session, user_id: int) -> User:
    locked = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not locked:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return locked


def quota_info(db: Session, user: User) -> dict:
    from app.services.cloud_quota import quota_breakdown, user_quota_bytes

    fresh = db.get(User, user.id)
    if not fresh:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.refresh(fresh)

    breakdown = quota_breakdown(db, fresh)
    return {
        "used_bytes": used_bytes(db, fresh.id),
        "reserved_bytes": reserved_bytes(db, fresh.id),
        "uploading_count": uploading_count(db, fresh.id),
        "max_concurrent_uploads": max_concurrent_uploads(),
        "quota_bytes": user_quota_bytes(db, fresh),
        "base_bytes": breakdown["base_bytes"],
        "vps_bonus_bytes": breakdown["vps_bonus_bytes"],
        "subscribed_bytes": breakdown["subscribed_bytes"],
        "bonus_bytes": breakdown["bonus_bytes"],
        "extra_bytes": breakdown["extra_bytes"],
        "contracted_gb": breakdown["contracted_gb"],
        "billing": breakdown["billing"],
        "chunk_size_bytes": chunk_size_bytes(),
        "max_upload_bytes": max_upload_bytes(),
    }


def storage_status() -> dict:
    discord = get_discord_storage()
    backend = _active_backend()
    status = {
        "storage_backend": backend,
        "discord_configured": discord.configured,
        "bandwidth_limit_mbps": _settings().cloud_files_bandwidth_limit_mbps,
        "max_upload_bytes": max_upload_bytes(),
        "chunk_size_bytes": chunk_size_bytes(),
        "discord_ok": False,
        "bot_count": discord.bot_count,
        "bots_ok": 0,
        "bots": [],
        # Rotas exigidas pelo frontend atual (upload com progresso e limpeza).
        "api_features": ["progress", "sync_pending", "cleanup_incomplete"],
    }
    if backend == "discord" and discord.configured:
        health = discord.get_cached_health()
        if health:
            status["discord_ok"] = health.get("ok", False)
            status.update(
                {
                    "bot_count": health.get("bot_count", discord.bot_count),
                    "bots_ok": health.get("bots_ok", 0),
                    "bots": health.get("bots", []),
                    "bot_username": health.get("bot_username"),
                    "channel_name": health.get("channel_name"),
                }
            )
        else:
            status["discord_check_pending"] = True
            discord.refresh_health_async()
    return status


def list_files(db: Session, user: User, parent_id: int | None) -> list[CloudFile]:
    _resolve_parent(db, user, parent_id)
    query = db.query(CloudFile).filter(CloudFile.user_id == user.id)
    query = _filter_by_parent(query, parent_id)
    return query.order_by(CloudFile.is_folder.desc(), CloudFile.name.asc()).all()


def create_folder(db: Session, user: User, name: str, parent_id: int | None) -> CloudFile:
    name = _sanitize_name(name)
    _resolve_parent(db, user, parent_id)
    if _duplicate_name(db, user.id, parent_id, name):
        raise HTTPException(status_code=400, detail="Já existe um item com esse nome")

    folder = CloudFile(
        user_id=user.id,
        parent_id=parent_id,
        name=name,
        is_folder=True,
        storage_backend=_active_backend(),
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def start_upload(
    db: Session,
    user: User,
    name: str,
    parent_id: int | None,
    size_bytes: int,
    total_chunks: int,
    mime_type: str | None,
    *,
    replace_existing: bool = False,
) -> tuple[CloudFile, bool, str | None]:
    if _uses_discord():
        get_discord_storage()._require_config()

    name = _sanitize_name(name)
    requested_name = name
    _resolve_parent(db, user, parent_id)

    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    upload_limit = max_upload_bytes()
    chunk_size = chunk_size_bytes()
    if size_bytes > upload_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo excede o limite de {fmt_bytes(upload_limit)}",
        )
    expected_chunks = max(1, math.ceil(size_bytes / chunk_size))
    if total_chunks != expected_chunks:
        raise HTTPException(
            status_code=400,
            detail="Número de fragmentos não confere com o tamanho do arquivo",
        )

    from app.services.billing import assert_cloud_billing_allows_upload
    from app.services.cloud_quota import user_quota_bytes

    _lock_user(db, user.id)
    assert_cloud_billing_allows_upload(user)
    quota_limit = user_quota_bytes(db, user)

    matches = _files_with_name(db, user.id, parent_id, name, folders=False)
    uploading = [m for m in matches if m.upload_status == "uploading"]
    if uploading:
        record = uploading[0]
        current = used_bytes(db, user.id, exclude_file_id=record.id)
        assert_upload_quota(current, size_bytes, quota_limit)
        record.size_bytes = size_bytes
        record.chunk_count = total_chunks
        record.mime_type = mime_type
        _file_dir(user.id, record.id)
        db.commit()
        db.refresh(record)
        log_info(
            logger,
            TAG_CLOUD,
            "Upload retomado file_id=%s nome=%r chunks=%s tamanho=%s user_id=%s",
            record.id,
            name,
            total_chunks,
            fmt_bytes(size_bytes),
            user.id,
        )
        return record, True, None

    ready_matches = [m for m in matches if m.upload_status == "ready"]
    if ready_matches:
        if replace_existing:
            for stale in ready_matches:
                _delete_tree(db, user.id, stale)
            matches = [m for m in matches if m.upload_status != "ready"]
        else:
            unique_name = _unique_upload_name(db, user.id, parent_id, name)
            if unique_name != name:
                log_info(
                    logger,
                    TAG_CLOUD,
                    "Nome de upload ajustado %r -> %r user_id=%s",
                    name,
                    unique_name,
                    user.id,
                )
                name = unique_name
                matches = []

    if matches:
        for stale in matches:
            log_info(
                logger,
                TAG_CLOUD,
                "Removendo registro stale file_id=%s status=%s nome=%r",
                stale.id,
                stale.upload_status,
                stale.name,
            )
            _delete_tree(db, user.id, stale)

    current = used_bytes(db, user.id)
    assert_upload_quota(current, size_bytes, quota_limit)
    assert_upload_concurrency(uploading_count(db, user.id), max_concurrent_uploads())

    backend = _active_backend()
    record = CloudFile(
        user_id=user.id,
        parent_id=parent_id,
        name=name,
        is_folder=False,
        size_bytes=size_bytes,
        mime_type=mime_type,
        chunk_count=total_chunks,
        storage_backend=backend,
        upload_status="uploading",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if backend == "local":
        _file_dir(user.id, record.id)

    log_info(
        logger,
        TAG_CLOUD,
        "Upload iniciado file_id=%s nome=%r chunks=%s tamanho=%s backend=%s user_id=%s",
        record.id,
        name,
        total_chunks,
        fmt_bytes(size_bytes),
        backend,
        user.id,
    )
    renamed_from = requested_name if name != requested_name else None
    return record, False, renamed_from


def get_upload_progress(db: Session, user: User, file_id: int) -> dict:
    record = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.user_id == user.id, CloudFile.is_folder.is_(False))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    chunks = (
        db.query(CloudFileChunk)
        .filter(CloudFileChunk.file_id == file_id)
        .order_by(CloudFileChunk.chunk_index.asc())
        .all()
    )
    received_indices = [
        c.chunk_index
        for c in chunks
        if c.discord_message_id or _chunk_path(user.id, file_id, c.chunk_index).exists()
    ]
    synced_indices = [c.chunk_index for c in chunks if c.discord_message_id]

    progress = {
        "file_id": file_id,
        "chunk_count": record.chunk_count,
        "received_chunks": len(received_indices),
        "synced_chunks": len(synced_indices),
        "received_indices": received_indices,
        "synced_indices": synced_indices,
        "upload_status": record.upload_status,
    }
    if record.upload_status == "uploading":
        log_progress(
            logger,
            TAG_CLOUD,
            f"Progresso upload file_id={file_id} nome={record.name!r}",
            len(synced_indices),
            record.chunk_count,
            recebidos=len(received_indices),
        )
    return progress


def list_pending_sync_chunks(db: Session, user_id: int, file_id: int) -> list[int]:
    chunks = db.query(CloudFileChunk).filter(CloudFileChunk.file_id == file_id).all()
    pending: list[int] = []
    for chunk in chunks:
        if chunk.discord_message_id:
            continue
        if _chunk_path(user_id, file_id, chunk.chunk_index).exists():
            pending.append(chunk.chunk_index)
    return sorted(pending)


def sync_chunk_to_discord(file_id: int, chunk_index: int, user_id: int) -> None:
    db = SessionLocal()
    try:
        record = db.query(CloudFile).filter(CloudFile.id == file_id).first()
        file_name = record.name if record else "?"
        total = record.chunk_count if record else "?"

        chunk = (
            db.query(CloudFileChunk)
            .filter(CloudFileChunk.file_id == file_id, CloudFileChunk.chunk_index == chunk_index)
            .first()
        )
        if chunk and chunk.discord_message_id:
            log_info(
                logger,
                TAG_CLOUD,
                "Sync ignorado (já no Discord) file_id=%s chunk=%s/%s",
                file_id,
                chunk_index + 1,
                total,
            )
            return

        path = _chunk_path(user_id, file_id, chunk_index)
        if not path.exists():
            log_info(
                logger,
                TAG_CLOUD,
                "Sync ignorado (sem buffer local) file_id=%s chunk=%s/%s",
                file_id,
                chunk_index + 1,
                total,
            )
            return

        data = path.read_bytes()
        log_info(
            logger,
            TAG_CLOUD,
            "Sync Discord iniciado file_id=%s chunk=%s/%s tamanho=%s nome=%r",
            file_id,
            chunk_index + 1,
            total,
            fmt_bytes(len(data)),
            file_name,
        )
        discord = get_discord_storage()
        channel_id, message_id, attachment_id, attachment_url, bot_index = discord.upload_chunk(
            file_id=file_id,
            chunk_index=chunk_index,
            data=data,
        )
        now = datetime.utcnow()
        if chunk:
            chunk.size_bytes = len(data)
            chunk.discord_channel_id = channel_id
            chunk.discord_message_id = message_id
            chunk.discord_attachment_id = attachment_id
            chunk.discord_attachment_url = attachment_url
            chunk.discord_url_cached_at = now
            chunk.discord_bot_index = bot_index
        else:
            db.add(
                CloudFileChunk(
                    file_id=file_id,
                    chunk_index=chunk_index,
                    size_bytes=len(data),
                    discord_channel_id=channel_id,
                    discord_message_id=message_id,
                    discord_attachment_id=attachment_id,
                    discord_attachment_url=attachment_url,
                    discord_url_cached_at=now,
                    discord_bot_index=bot_index,
                )
            )
        db.commit()
        path.unlink(missing_ok=True)

        synced = (
            db.query(CloudFileChunk)
            .filter(CloudFileChunk.file_id == file_id, CloudFileChunk.discord_message_id.isnot(None))
            .count()
        )
        log_info(
            logger,
            TAG_CLOUD,
            "Sync Discord OK file_id=%s chunk=%s/%s bot=#%s msg=%s | total_discord=%s/%s",
            file_id,
            chunk_index + 1,
            total,
            bot_index + 1,
            message_id,
            synced,
            total,
        )
    except Exception as exc:
        log_exception(
            logger,
            TAG_CLOUD,
            "Sync Discord FALHOU file_id=%s chunk=%s: %s",
            file_id,
            chunk_index,
            exc,
        )
        raise
    finally:
        db.close()


def sync_pending_parallel(file_id: int, user_id: int, chunk_indices: list[int]) -> int:
    """Sincroniza fragmentos pendentes. Retorna quantidade de falhas."""
    if not chunk_indices:
        log_info(logger, TAG_CLOUD, "Sync paralelo: nada pendente file_id=%s", file_id)
        return 0
    from concurrent.futures import ThreadPoolExecutor, as_completed

    discord = get_discord_storage()
    workers = min(max(1, discord.bot_count), len(chunk_indices), 10)
    log_info(
        logger,
        TAG_CLOUD,
        "Sync paralelo iniciado file_id=%s pendentes=%s workers=%s bots=%s",
        file_id,
        len(chunk_indices),
        workers,
        discord.bot_count,
    )
    done = 0
    failures = 0
    total = len(chunk_indices)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(sync_chunk_to_discord, file_id, chunk_index, user_id)
            for chunk_index in chunk_indices
        ]
        for future in as_completed(futures):
            done += 1
            try:
                future.result()
            except Exception:
                failures += 1
                log_exception(logger, TAG_CLOUD, "Falha no sync paralelo file_id=%s", file_id)
            log_progress(logger, TAG_CLOUD, f"Sync paralelo file_id={file_id}", done, total)
    log_info(
        logger,
        TAG_CLOUD,
        "Sync paralelo concluído file_id=%s total=%s falhas=%s",
        file_id,
        total,
        failures,
    )
    return failures


def _save_chunk_local(
    db: Session,
    user: User,
    file_id: int,
    chunk_index: int,
    data: bytes,
) -> None:
    dest = _chunk_path(user.id, file_id, chunk_index)
    dest.write_bytes(data)
    _upsert_chunk_record(db, file_id, chunk_index, len(data))


def _upsert_chunk_record(
    db: Session, file_id: int, chunk_index: int, size_bytes: int, *, reset_discord: bool = False
) -> None:
    existing = (
        db.query(CloudFileChunk)
        .filter(CloudFileChunk.file_id == file_id, CloudFileChunk.chunk_index == chunk_index)
        .first()
    )
    if existing:
        existing.size_bytes = size_bytes
        if reset_discord:
            existing.discord_message_id = None
            existing.discord_channel_id = None
            existing.discord_attachment_id = None
            existing.discord_attachment_url = None
            existing.discord_url_cached_at = None
            existing.discord_bot_index = None
    else:
        db.add(
            CloudFileChunk(
                file_id=file_id,
                chunk_index=chunk_index,
                size_bytes=size_bytes,
            )
        )


def _chunk_record_for_upload(db: Session, user: User, file_id: int, chunk_index: int) -> CloudFile:
    record = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.user_id == user.id, CloudFile.is_folder.is_(False))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    if record.upload_status not in ("uploading", "ready"):
        raise HTTPException(status_code=400, detail="Upload não está ativo")
    if chunk_index < 0 or chunk_index >= record.chunk_count:
        raise HTTPException(status_code=400, detail="Índice de fragmento inválido")
    return record


def save_chunk_stream(
    db: Session,
    user: User,
    file_id: int,
    chunk_index: int,
    raw_file,
) -> tuple[bool, int]:
    """Grava o fragmento em disco por streaming. Retorna (precisa_discord, bytes)."""
    record = _chunk_record_for_upload(db, user, file_id, chunk_index)
    dest = _chunk_path(user.id, file_id, chunk_index)
    max_bytes = expected_chunk_size(
        int(record.size_bytes or 0),
        int(record.chunk_count or 0),
        chunk_index,
        chunk_size_bytes(),
    )
    if max_bytes <= 0:
        raise HTTPException(status_code=400, detail="Fragmento inválido para o tamanho reservado")
    _file_dir(user.id, file_id)
    try:
        written = bandwidth_limiter.stream_to_path(raw_file, dest, max_bytes=max_bytes)
    except bandwidth_limiter.EmptyTransfer:
        raise HTTPException(status_code=400, detail="Fragmento vazio")
    except bandwidth_limiter.TransferLimitExceeded:
        raise HTTPException(
            status_code=413,
            detail=f"Fragmento excede {fmt_bytes(max_bytes)}",
        )

    needs_discord = _uses_discord(record)
    _upsert_chunk_record(db, file_id, chunk_index, written, reset_discord=needs_discord)
    if needs_discord:
        _invalidate_assembled_cache(user.id, file_id)
    db.commit()
    log_progress(
        logger,
        TAG_CLOUD,
        f"Fragmento recebido file_id={file_id} nome={record.name!r}",
        chunk_index + 1,
        record.chunk_count,
        bytes=fmt_bytes(written),
    )
    return needs_discord, written


def save_chunk_bytes(
    db: Session,
    user: User,
    file_id: int,
    chunk_index: int,
    data: bytes,
) -> bool:
    """Compatível com testes: encaminha para o caminho de streaming."""
    needs_discord, _written = save_chunk_stream(
        db, user, file_id, chunk_index, io.BytesIO(data)
    )
    return needs_discord


def save_chunk(
    db: Session,
    user: User,
    file_id: int,
    chunk_index: int,
    upload: UploadFile,
) -> bool:
    """Salva fragmento. Retorna True se precisa sincronizar com Discord em background."""
    needs_discord, _written = save_chunk_stream(
        db, user, file_id, chunk_index, upload.file
    )
    return needs_discord


def complete_upload(db: Session, user: User, file_id: int) -> CloudFile:
    record = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.user_id == user.id, CloudFile.is_folder.is_(False))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    chunks = (
        db.query(CloudFileChunk)
        .filter(CloudFileChunk.file_id == file_id)
        .order_by(CloudFileChunk.chunk_index.asc())
        .all()
    )
    if len(chunks) != record.chunk_count:
        raise HTTPException(status_code=400, detail="Upload incompleto")

    if _uses_discord(record):
        synced = sum(1 for c in chunks if c.discord_message_id)
        if synced != record.chunk_count:
            log_info(
                logger,
                TAG_CLOUD,
                "Complete bloqueado file_id=%s nome=%r discord=%s/%s",
                file_id,
                record.name,
                synced,
                record.chunk_count,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Ainda sincronizando com Discord ({synced}/{record.chunk_count} fragmentos)",
            )
        record.size_bytes = sum(c.size_bytes for c in chunks)
    else:
        assembled = _assembled_path(user.id, file_id)
        with assembled.open("wb") as out:
            for chunk in chunks:
                part = _chunk_path(user.id, file_id, chunk.chunk_index)
                if not part.exists():
                    raise HTTPException(status_code=400, detail="Fragmento ausente no disco")
                with part.open("rb") as src:
                    shutil.copyfileobj(src, out, length=64 * 1024)
        record.size_bytes = assembled.stat().st_size

    record.upload_status = "ready"
    db.commit()
    db.refresh(record)
    log_info(
        logger,
        TAG_CLOUD,
        "Upload concluído file_id=%s nome=%r tamanho=%s chunks=%s",
        file_id,
        record.name,
        fmt_bytes(record.size_bytes),
        record.chunk_count,
    )
    return record


def _resolve_chunk_url(db: Session, chunk: CloudFileChunk, *, commit: bool = True) -> str:
    discord = get_discord_storage()
    if chunk.discord_attachment_url and discord.url_cache_valid(chunk.discord_url_cached_at):
        log_info(
            logger,
            TAG_CLOUD,
            "URL cache hit file_id=%s chunk=%s bot=#%s",
            chunk.file_id,
            chunk.chunk_index + 1,
            (chunk.discord_bot_index or 0) + 1,
        )
        return chunk.discord_attachment_url

    if not chunk.discord_message_id or not chunk.discord_channel_id:
        raise HTTPException(status_code=404, detail="Fragmento Discord incompleto")

    log_info(
        logger,
        TAG_CLOUD,
        "Renovando URL Discord file_id=%s chunk=%s bot=#%s msg=%s",
        chunk.file_id,
        chunk.chunk_index + 1,
        (chunk.discord_bot_index or 0) + 1,
        chunk.discord_message_id,
    )
    url = discord.resolve_attachment_url(
        chunk.discord_channel_id,
        chunk.discord_message_id,
        chunk.discord_attachment_id,
        chunk.discord_bot_index if chunk.discord_bot_index is not None else 0,
        chunk.chunk_index,
    )
    chunk.discord_attachment_url = url
    chunk.discord_url_cached_at = datetime.utcnow()
    if commit:
        db.commit()
    return url


def _invalidate_assembled_cache(user_id: int, file_id: int) -> None:
    path = _assembled_path(user_id, file_id)
    if path.exists():
        path.unlink()


def _ensure_discord_assembled(
    db: Session,
    user_id: int,
    file_id: int,
    record: CloudFile,
    chunks: list[CloudFileChunk],
) -> Path:
    path = _assembled_path(user_id, file_id)
    if path.exists() and path.stat().st_size == record.size_bytes:
        log_info(
            logger,
            TAG_CLOUD,
            "Download cache hit file_id=%s nome=%r tamanho=%s",
            file_id,
            record.name,
            fmt_bytes(path.stat().st_size),
        )
        return path

    log_info(
        logger,
        TAG_CLOUD,
        "Montando arquivo do Discord file_id=%s nome=%r chunks=%s",
        file_id,
        record.name,
        len(chunks),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    discord = get_discord_storage()
    limit = max(chunk_size_bytes(), _settings().discord_attachment_limit_bytes)
    try:
        with path.open("wb") as out:
            for i, chunk in enumerate(chunks, start=1):
                url = _resolve_chunk_url(db, chunk, commit=False)
                log_progress(
                    logger,
                    TAG_CLOUD,
                    f"Baixando fragmento file_id={file_id}",
                    i,
                    len(chunks),
                )
                for block in discord.download_attachment(url, max_bytes=limit):
                    out.write(block)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    db.commit()
    log_info(
        logger,
        TAG_CLOUD,
        "Arquivo montado file_id=%s nome=%r tamanho=%s path=%s",
        file_id,
        record.name,
        fmt_bytes(path.stat().st_size),
        path,
    )
    return path


def get_download(db: Session, user: User, file_id: int) -> DownloadResult:
    record = (
        db.query(CloudFile)
        .filter(
            CloudFile.id == file_id,
            CloudFile.user_id == user.id,
            CloudFile.is_folder.is_(False),
            CloudFile.upload_status == "ready",
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    log_info(
        logger,
        TAG_CLOUD,
        "Download solicitado file_id=%s nome=%r user_id=%s backend=%s",
        file_id,
        record.name,
        user.id,
        record.storage_backend,
    )

    if _uses_discord(record):
        chunks = (
            db.query(CloudFileChunk)
            .filter(CloudFileChunk.file_id == file_id)
            .order_by(CloudFileChunk.chunk_index.asc())
            .all()
        )
        if len(chunks) != record.chunk_count:
            raise HTTPException(status_code=404, detail="Fragmentos do arquivo incompletos")
        path = _ensure_discord_assembled(db, user.id, file_id, record, chunks)
        log_info(logger, TAG_CLOUD, "Download pronto file_id=%s path=%s", file_id, path)
        return DownloadResult(record=record, path=path)

    path = _assembled_path(user.id, file_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conteúdo do arquivo indisponível")
    log_info(logger, TAG_CLOUD, "Download local file_id=%s path=%s", file_id, path)
    return DownloadResult(record=record, path=path)


def _delete_tree(db: Session, user_id: int, node: CloudFile) -> None:
    if node.is_folder:
        children = db.query(CloudFile).filter(CloudFile.parent_id == node.id).all()
        for child in children:
            _delete_tree(db, user_id, child)
    else:
        enqueue_chunk_tombstones(db, user_id, node)
        shutil.rmtree(_file_dir(user_id, node.id), ignore_errors=True)
    db.delete(node)
    # Flush por nó: MySQL exige apagar filhos antes do pai (FK parent_id).
    db.flush()


def cleanup_incomplete_uploads(db: Session, user: User, parent_id: int | None = None) -> int:
    """Remove uploads incompletos (status=uploading). Retorna quantidade removida."""
    query = db.query(CloudFile).filter(
        CloudFile.user_id == user.id,
        CloudFile.is_folder.is_(False),
        CloudFile.upload_status == "uploading",
    )
    query = _filter_by_parent(query, parent_id)
    stale = query.all()
    for record in stale:
        log_info(
            logger,
            TAG_CLOUD,
            "Limpando incompleto file_id=%s nome=%r user_id=%s",
            record.id,
            record.name,
            user.id,
        )
        _delete_tree(db, user.id, record)
    if stale:
        db.commit()
        schedule_discord_purge()
    return len(stale)


def _is_descendant_of(db: Session, node_id: int | None, ancestor_id: int) -> bool:
    current = node_id
    visited: set[int] = set()
    while current is not None:
        if current == ancestor_id:
            return True
        if current in visited:
            break
        visited.add(current)
        row = db.query(CloudFile.parent_id).filter(CloudFile.id == current).first()
        if not row:
            break
        current = row[0]
    return False


def move_nodes(db: Session, user: User, node_ids: list[int], dest_parent_id: int | None) -> int:
    if not node_ids:
        raise HTTPException(status_code=400, detail="Nenhum item selecionado")

    _resolve_parent(db, user, dest_parent_id)

    nodes = (
        db.query(CloudFile)
        .filter(CloudFile.id.in_(node_ids), CloudFile.user_id == user.id)
        .all()
    )
    if len(nodes) != len(set(node_ids)):
        raise HTTPException(status_code=404, detail="Item não encontrado")

    moving_ids = {n.id for n in nodes}

    for node in nodes:
        if not node.is_folder and node.upload_status == "uploading":
            raise HTTPException(
                status_code=400,
                detail=f'"{node.name}" ainda está em upload — aguarde ou exclua',
            )

    for node in nodes:
        if node.parent_id == dest_parent_id:
            continue
        if node.is_folder:
            if dest_parent_id == node.id:
                raise HTTPException(
                    status_code=400,
                    detail=f'Não é possível mover "{node.name}" para dentro de si mesma',
                )
            if dest_parent_id is not None and _is_descendant_of(db, dest_parent_id, node.id):
                raise HTTPException(
                    status_code=400,
                    detail=f'Não é possível mover "{node.name}" para uma subpasta',
                )
        if dest_parent_id in moving_ids:
            raise HTTPException(
                status_code=400,
                detail="Não é possível mover para um item que também está sendo movido",
            )
        if _duplicate_name(db, user.id, dest_parent_id, node.name):
            matches = _files_with_name(db, user.id, dest_parent_id, node.name)
            if not any(m.id == node.id for m in matches):
                raise HTTPException(
                    status_code=400,
                    detail=f'Já existe "{node.name}" no destino',
                )

    moved = 0
    for node in nodes:
        if node.parent_id == dest_parent_id:
            continue
        log_info(
            logger,
            TAG_CLOUD,
            "Movendo file_id=%s nome=%r para parent_id=%s user_id=%s",
            node.id,
            node.name,
            dest_parent_id,
            user.id,
        )
        node.parent_id = dest_parent_id
        moved += 1

    if moved:
        db.commit()
    return moved


def delete_all_for_user(db: Session, user: User) -> int:
    """Remove a árvore CyberCloud do usuário. Não faz commit."""
    total = db.query(CloudFile).filter(CloudFile.user_id == user.id).count()
    roots = (
        db.query(CloudFile)
        .filter(CloudFile.user_id == user.id, CloudFile.parent_id.is_(None))
        .all()
    )
    for node in roots:
        _delete_tree(db, user.id, node)
    leftover = db.query(CloudFile).filter(CloudFile.user_id == user.id).first()
    for _ in range(10_000):
        if leftover is None:
            break
        _delete_tree(db, user.id, leftover)
        leftover = db.query(CloudFile).filter(CloudFile.user_id == user.id).first()
    else:
        raise HTTPException(status_code=500, detail="Não foi possível apagar todos os arquivos da conta")
    user_dir = _storage_root() / str(int(user.id))
    if user_dir.exists() and is_under_root(user_dir, _storage_root()):
        shutil.rmtree(user_dir, ignore_errors=True)
    if total:
        schedule_discord_purge()
        log_info(logger, TAG_CLOUD, "Árvore CyberCloud apagada user_id=%s itens=%s", user.id, total)
    return total


def delete_node(db: Session, user: User, file_id: int) -> None:
    record = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    log_info(
        logger,
        TAG_CLOUD,
        "Excluindo file_id=%s nome=%r pasta=%s user_id=%s",
        file_id,
        record.name,
        record.is_folder,
        user.id,
    )
    _delete_tree(db, user.id, record)
    db.commit()
    schedule_discord_purge()
    log_info(logger, TAG_CLOUD, "Excluído file_id=%s", file_id)
