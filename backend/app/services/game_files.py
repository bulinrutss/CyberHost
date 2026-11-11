"""Gestão de arquivos do servidor de jogo no diretório do cliente."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings
from app.models.game_server import GameServer
from app.services.cloud_log import fmt_bytes
from app.services.game_sandbox import is_under_root


def max_edit_bytes() -> int:
    return max(1, int(get_settings().game_files_max_edit_bytes))


def max_upload_bytes() -> int:
    return max(1, int(get_settings().game_files_max_upload_bytes))


def quota_bytes() -> int:
    return max(1, int(get_settings().game_files_quota_bytes))


def _server_root(server: GameServer) -> Path:
    root = Path(server.data_path).resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(server: GameServer, relative: str) -> Path:
    root = _server_root(server)
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    if rel in ("", "."):
        target = root
    else:
        target = (root / rel).resolve()
    if not is_under_root(target, root):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    internal = root / ".cyberhost"
    if is_under_root(target, internal):
        raise HTTPException(status_code=403, detail="Caminho reservado pelo sistema")
    return target


def _file_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    return 0


def tree_used_bytes(server: GameServer) -> int:
    root = _server_root(server)
    total = 0
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if ".cyberhost" in relative.parts:
            continue
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _assert_quota(server: GameServer, incoming: int, dest: Path) -> None:
    used = tree_used_bytes(server)
    projected = used - _file_size(dest) + incoming
    limit = quota_bytes()
    if projected > limit:
        raise HTTPException(
            status_code=400,
            detail=f"Cota de arquivos do servidor excedida ({fmt_bytes(limit)})",
        )


def _stream_to_path(raw_file, dest: Path, max_bytes: int) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    written = 0
    try:
        with tmp.open("wb") as out:
            while True:
                block = raw_file.read(65536)
                if not block:
                    break
                written += len(block)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Arquivo excede {fmt_bytes(max_bytes)}",
                    )
                out.write(block)
        if written == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio")
        tmp.replace(dest)
        return written
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def list_directory(server: GameServer, relative: str = "") -> list[dict]:
    target = _safe_path(server, relative)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Diretório não encontrado")
    items = []
    for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if entry.name == ".cyberhost":
            continue
        rel = entry.relative_to(_server_root(server)).as_posix()
        items.append(
            {
                "name": entry.name,
                "path": rel,
                "is_dir": entry.is_dir(),
                "size_bytes": entry.stat().st_size if entry.is_file() else 0,
            }
        )
    return items


def read_file(server: GameServer, relative: str) -> str:
    target = _safe_path(server, relative)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    limit = max_edit_bytes()
    if target.stat().st_size > limit:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo muito grande para edição no painel (máx. {fmt_bytes(limit)})",
        )
    return target.read_text(encoding="utf-8", errors="replace")


def write_file(server: GameServer, relative: str, content: str) -> None:
    target = _safe_path(server, relative)
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Caminho é um diretório")
    data = content.encode("utf-8")
    limit = max_edit_bytes()
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de edição ({fmt_bytes(limit)})",
        )
    _assert_quota(server, len(data), target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def upload_file(server: GameServer, relative_dir: str, upload: UploadFile) -> dict:
    target_dir = _safe_path(server, relative_dir)
    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
    name = (upload.filename or "upload.bin").replace("\\", "/").split("/")[-1]
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    dest = _safe_path(server, f"{relative_dir.rstrip('/')}/{name}".lstrip("/"))
    remaining = quota_bytes() - (tree_used_bytes(server) - _file_size(dest))
    if remaining <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cota de arquivos do servidor excedida ({fmt_bytes(quota_bytes())})",
        )
    cap = min(max_upload_bytes(), remaining)
    written = _stream_to_path(upload.file, dest, cap)
    return {
        "name": name,
        "path": dest.relative_to(_server_root(server)).as_posix(),
        "size_bytes": written,
    }
