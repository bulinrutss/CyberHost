"""Arquivos do site (pasta public/), com cota em disco do plano."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings
from app.models.web_site import WebSite
from app.services.cloud_log import fmt_bytes
from app.services.web_sandbox import is_under_root


def max_edit_bytes() -> int:
    return max(1, int(get_settings().web_files_max_edit_bytes))


def max_upload_bytes() -> int:
    return max(1, int(get_settings().web_files_max_upload_bytes))


def quota_bytes(site: WebSite) -> int:
    return max(1, int(site.disk_mb) * 1024 * 1024)


def _site_root(site: WebSite) -> Path:
    root = Path(site.data_path).resolve() / "public"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(site: WebSite, relative: str) -> Path:
    root = _site_root(site)
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    if rel in ("", "."):
        target = root
    else:
        target = (root / rel).resolve()
    if not is_under_root(target, root):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return target


def _file_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    return 0


def tree_used_bytes(site: WebSite) -> int:
    root = _site_root(site)
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _assert_quota(site: WebSite, incoming: int, dest: Path) -> None:
    used = tree_used_bytes(site)
    projected = used - _file_size(dest) + incoming
    limit = quota_bytes(site)
    if projected > limit:
        raise HTTPException(
            status_code=400,
            detail=f"Cota de disco do site excedida ({fmt_bytes(limit)})",
        )


def list_directory(site: WebSite, relative: str = "") -> list[dict]:
    target = _safe_path(site, relative)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Diretório não encontrado")
    items = []
    for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel = entry.relative_to(_site_root(site)).as_posix()
        items.append(
            {
                "name": entry.name,
                "path": rel,
                "is_dir": entry.is_dir(),
                "size_bytes": _file_size(entry) if entry.is_file() else 0,
            }
        )
    return items


def read_file(site: WebSite, relative: str) -> dict:
    target = _safe_path(site, relative)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    if target.stat().st_size > max_edit_bytes():
        raise HTTPException(status_code=413, detail="Arquivo grande demais para editar")
    return {"path": relative, "content": target.read_text(encoding="utf-8", errors="replace")}


def write_file(site: WebSite, relative: str, content: str) -> None:
    data = content.encode("utf-8")
    if len(data) > max_edit_bytes():
        raise HTTPException(status_code=413, detail=f"Edição excede {fmt_bytes(max_edit_bytes())}")
    dest = _safe_path(site, relative)
    if dest.is_dir():
        raise HTTPException(status_code=400, detail="Caminho é uma pasta")
    _assert_quota(site, len(data), dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def _normalize_relative(relative: str) -> str:
    return (relative or "").strip().replace("\\", "/").strip("/")


def _join_relative(base: str, name: str) -> str:
    base = _normalize_relative(base)
    name = name.strip().replace("\\", "/").strip("/")
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nome inválido")
    if ".." in name.split("/"):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return f"{base}/{name}" if base else name


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
                    raise HTTPException(status_code=413, detail=f"Arquivo excede {fmt_bytes(max_bytes)}")
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


def create_directory(site: WebSite, relative_dir: str, name: str) -> dict:
    folder_name = name.strip().replace("\\", "/").strip("/")
    if not folder_name or "/" in folder_name or folder_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nome de pasta inválido")
    full_rel = _join_relative(relative_dir, folder_name)
    dest = _safe_path(site, full_rel)
    if dest.exists():
        raise HTTPException(status_code=400, detail="Já existe")
    dest.mkdir(parents=True, exist_ok=False)
    return {
        "name": folder_name,
        "path": full_rel,
        "is_dir": True,
        "size_bytes": 0,
    }
def upload_file(site: WebSite, relative_dir: str, file: UploadFile) -> dict:
    rel_name = (file.filename or "upload.bin").replace("\\", "/").strip().lstrip("/")
    if not rel_name or rel_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    if ".." in rel_name.split("/"):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    full_rel = _join_relative(relative_dir, rel_name)
    dest = _safe_path(site, full_rel)
    if dest.is_dir():
        raise HTTPException(status_code=400, detail="Caminho é uma pasta")
    if not is_under_root(dest, _site_root(site)):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    limit = max_upload_bytes()
    written = _stream_to_path(file.file, dest, limit)
    _assert_quota(site, written, dest)
    return {
        "name": Path(rel_name).name,
        "path": dest.relative_to(_site_root(site)).as_posix(),
        "is_dir": False,
        "size_bytes": written,
    }


def delete_path(site: WebSite, relative: str) -> None:
    root = _site_root(site)
    rel = _normalize_relative(relative)
    if not rel:
        raise HTTPException(status_code=400, detail="Não é possível apagar a pasta raiz")
    target = _safe_path(site, rel)
    if target == root:
        raise HTTPException(status_code=400, detail="Não é possível apagar a pasta raiz")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Não encontrado")
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()
