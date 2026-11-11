from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings
from app.models.finance import FinanceTransaction
from app.services.game_sandbox import is_under_root

ALLOWED_EXT = {"jpg", "png", "webp"}
_MIME = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def max_bytes() -> int:
    return max(1, int(get_settings().finance_receipt_max_bytes))


def receipts_root() -> Path:
    root = Path(get_settings().finance_receipts_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def mime_for(ext: str | None) -> str:
    return _MIME.get((ext or "").lower(), "application/octet-stream")


def sniff_image(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _user_dir(user_id: int) -> Path:
    root = receipts_root()
    folder = (root / str(int(user_id))).resolve()
    if not is_under_root(folder, root):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def receipt_path(user_id: int, tx_id: int, ext: str) -> Path:
    root = receipts_root()
    ext = ext.lower().strip(".")
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Tipo de imagem não suportado")
    path = (_user_dir(user_id) / f"{int(tx_id)}.{ext}").resolve()
    if not is_under_root(path, root):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return path


def delete_receipt_files(user_id: int, tx_id: int) -> None:
    root = receipts_root()
    folder = (_user_dir(user_id)).resolve()
    if not folder.is_dir() or not is_under_root(folder, root):
        return
    stem = str(int(tx_id))
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.stem != stem or path.suffix.lstrip(".").lower() not in ALLOWED_EXT:
            continue
        if is_under_root(path, root):
            path.unlink(missing_ok=True)


def save_receipt(row: FinanceTransaction, upload: UploadFile) -> str:
    raw = upload.file
    head = raw.read(16)
    ext = sniff_image(head)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie uma imagem JPG, PNG ou WEBP da nota fiscal",
        )
    cap = max_bytes()
    dest = receipt_path(row.user_id, row.id, ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    written = len(head)
    try:
        with tmp.open("wb") as out:
            out.write(head)
            while True:
                block = raw.read(65536)
                if not block:
                    break
                written += len(block)
                if written > cap:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="A nota fiscal pode ter no máximo 8 MB",
                    )
                out.write(block)
        if written == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio")
        delete_receipt_files(row.user_id, row.id)
        tmp.replace(dest)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return ext


def open_receipt(row: FinanceTransaction) -> Path:
    if not row.receipt_ext:
        raise HTTPException(status_code=404, detail="Nota fiscal não anexada")
    path = receipt_path(row.user_id, row.id, row.receipt_ext)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Nota fiscal não anexada")
    return path
