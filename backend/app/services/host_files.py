"""Explorador de arquivos do host Linux (painel admin)."""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import Settings, get_settings
from app.services.game_sandbox import is_under_root

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[^\\/:*?\"<>|\x00]{1,255}$")
_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".html",
    ".xml",
    ".sh",
    ".service",
    ".log",
    ".sql",
    ".example",
    ".local",
}


def max_edit_bytes(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    return max(1, int(settings.host_files_max_edit_bytes))


def max_upload_bytes(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    return max(1, int(settings.host_files_max_upload_bytes))


def allowed_roots(settings: Settings | None = None) -> list[Path]:
    settings = settings or get_settings()
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in settings.host_file_root_list:
        try:
            path = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if not path.is_dir():
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(path)
    return roots


def _under_any_root(path: Path, roots: list[Path]) -> Path | None:
    for root in roots:
        if is_under_root(path, root):
            return root
    return None


def resolve_host_path(raw: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    roots = allowed_roots(settings)
    if not roots:
        raise HTTPException(status_code=503, detail="Nenhuma pasta do host configurada")
    text = (raw or "").strip().replace("\\", "/")
    if not text:
        raise HTTPException(status_code=400, detail="Caminho obrigatório")
    candidate = Path(text)
    if not candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Use um caminho absoluto")
    try:
        target = candidate.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Caminho inválido") from exc
    if _under_any_root(target, roots) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    return target


def assert_child_name(name: str) -> str:
    value = (name or "").strip()
    if not value or value in {".", ".."} or not _NAME_RE.match(value):
        raise HTTPException(status_code=400, detail="Nome inválido")
    return value


def list_roots(settings: Settings | None = None) -> list[dict]:
    items = []
    for root in allowed_roots(settings):
        items.append(
            {
                "name": root.name or str(root),
                "path": str(root),
                "is_dir": True,
                "size": None,
                "modified_at": None,
            }
        )
    return items


def _stat_entry(path: Path) -> dict:
    try:
        info = path.lstat()
        is_dir = path.is_dir() and not path.is_symlink()
        if path.is_symlink():
            try:
                is_dir = path.resolve().is_dir() and _under_any_root(path.resolve(), allowed_roots()) is not None
            except OSError:
                is_dir = False
        mtime = datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).replace(tzinfo=None)
        return {
            "name": path.name,
            "path": str(path),
            "is_dir": is_dir,
            "size": None if is_dir else int(info.st_size),
            "modified_at": mtime,
        }
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível ler o item") from exc


def list_directory(raw_path: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    text = (raw_path or "").strip()
    roots = allowed_roots(settings)
    if not roots:
        raise HTTPException(status_code=503, detail="Nenhuma pasta do host configurada")
    if not text:
        return {"path": "", "parent": None, "entries": list_roots(settings)}

    directory = resolve_host_path(text, settings)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Não é uma pasta")

    entries: list[dict] = []
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível listar a pasta") from exc

    for child in sorted(children, key=lambda item: (not item.is_dir(), item.name.lower())):
        try:
            resolved = child.resolve()
        except OSError:
            continue
        if _under_any_root(resolved, roots) is None:
            continue
        entries.append(_stat_entry(child if child.is_symlink() else resolved))

    parent = str(directory.parent) if _under_any_root(directory.parent, roots) else ""
    if str(directory) in {str(root) for root in roots}:
        parent = ""
    return {"path": str(directory), "parent": parent, "entries": entries}


def _looks_text(path: Path, sample: bytes) -> bool:
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES or path.name.startswith(".env"):
        return b"\x00" not in sample
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def read_file(raw_path: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    path = resolve_host_path(raw_path, settings)
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Não é um arquivo")
    size = path.stat().st_size
    limit = max_edit_bytes(settings)
    if size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo maior que o limite de edição ({limit} bytes). Baixe em vez de editar.",
        )
    data = path.read_bytes()
    if not _looks_text(path, data[:4096]):
        raise HTTPException(status_code=415, detail="Arquivo binário — use o download")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("latin-1")
    logger.info("host files read path=%s size=%s", path, size)
    return {"path": str(path), "content": content, "size": size}


def write_file(raw_path: str, content: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    path = resolve_host_path(raw_path, settings)
    if path.exists() and path.is_dir():
        raise HTTPException(status_code=400, detail="Caminho é uma pasta")
    payload = content.encode("utf-8")
    limit = max_edit_bytes(settings)
    if len(payload) > limit:
        raise HTTPException(status_code=413, detail="Conteúdo maior que o limite de edição")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _under_any_root(path.parent.resolve(), allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    tmp = path.with_name(f".{path.name}.cyberhost-tmp")
    if _under_any_root(tmp.resolve(strict=False), allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    logger.info("host files write path=%s size=%s", path, len(payload))
    return {"path": str(path), "size": len(payload)}


def mkdir(raw_dir: str, name: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    directory = resolve_host_path(raw_dir, settings)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Pasta pai inválida")
    child = directory / assert_child_name(name)
    resolved = child.resolve()
    if _under_any_root(resolved, allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    if child.exists():
        raise HTTPException(status_code=400, detail="Já existe")
    child.mkdir()
    logger.info("host files mkdir path=%s", resolved)
    return _stat_entry(resolved)


def create_file(raw_dir: str, name: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    directory = resolve_host_path(raw_dir, settings)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Pasta pai inválida")
    child = directory / assert_child_name(name)
    resolved = child.resolve()
    if _under_any_root(resolved, allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    if child.exists():
        raise HTTPException(status_code=400, detail="Já existe")
    child.write_text("", encoding="utf-8")
    logger.info("host files create path=%s", resolved)
    return _stat_entry(resolved)


def rename_entry(raw_path: str, new_name: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    source = resolve_host_path(raw_path, settings)
    dest = source.parent / assert_child_name(new_name)
    resolved = dest.resolve()
    if _under_any_root(resolved, allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    if dest.exists():
        raise HTTPException(status_code=400, detail="Já existe")
    if str(source) in {str(root) for root in allowed_roots(settings)}:
        raise HTTPException(status_code=400, detail="Não é possível renomear a pasta raiz")
    source.rename(dest)
    logger.info("host files rename from=%s to=%s", source, resolved)
    return _stat_entry(resolved)


def delete_entry(raw_path: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = resolve_host_path(raw_path, settings)
    if str(path) in {str(root) for root in allowed_roots(settings)}:
        raise HTTPException(status_code=400, detail="Não é possível apagar a pasta raiz")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    logger.info("host files delete path=%s", path)


def upload_file(raw_dir: str, upload: UploadFile, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    directory = resolve_host_path(raw_dir, settings)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Pasta destino inválida")
    name = assert_child_name(Path(upload.filename or "").name or "upload.bin")
    dest = directory / name
    resolved = dest.resolve()
    if _under_any_root(resolved, allowed_roots(settings)) is None:
        raise HTTPException(status_code=400, detail="Caminho fora das pastas permitidas")
    limit = max_upload_bytes(settings)
    tmp = dest.with_name(f".{dest.name}.cyberhost-up")
    written = 0
    try:
        with tmp.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 256)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    handle.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Arquivo maior que o limite de upload")
                handle.write(chunk)
        os.replace(tmp, dest)
    except HTTPException:
        raise
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Falha ao gravar o arquivo") from exc
    logger.info("host files upload path=%s size=%s", resolved, written)
    return _stat_entry(resolved)


def download_path(raw_path: str, settings: Settings | None = None) -> Path:
    path = resolve_host_path(raw_path, settings)
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Não é um arquivo")
    logger.info("host files download path=%s", path)
    return path
