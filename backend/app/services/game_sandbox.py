"""Isolamento de processos de game: allowlist, unit systemd e validação de caminhos."""

from __future__ import annotations

import os
import re
from pathlib import Path

UNIT_PREFIX = "cyberhost-game-"
_UNIT_ID_RE = re.compile(r"^[1-9][0-9]{0,8}$")


def unit_name(server_id: int) -> str:
    if int(server_id) <= 0:
        raise ValueError("server_id inválido")
    return f"{UNIT_PREFIX}{int(server_id)}.service"


def parse_unit_server_id(name: str) -> int:
    raw = name.strip()
    if raw.endswith(".service"):
        raw = raw[: -len(".service")]
    if not raw.startswith(UNIT_PREFIX):
        raise ValueError("unit inválida")
    suffix = raw[len(UNIT_PREFIX) :]
    if not _UNIT_ID_RE.match(suffix):
        raise ValueError("unit inválida")
    return int(suffix)


def is_under_root(path: Path, root: Path) -> bool:
    """True se path está em root. Usa Path.is_relative_to, não prefixo textual."""
    try:
        resolved = path.resolve()
        base = root.resolve()
    except OSError:
        return False
    return resolved.is_relative_to(base)


def is_safe_cwd(cwd: Path, data_root: Path) -> bool:
    try:
        resolved = cwd.resolve()
    except OSError:
        return False
    return resolved.is_dir() and is_under_root(resolved, data_root)


def is_allowed_executable(executable: Path, data_root: Path, allow_bins: list[Path]) -> bool:
    try:
        exe = executable.resolve()
        root = data_root.resolve()
    except OSError:
        return False
    if not exe.is_file():
        return False
    if is_under_root(exe, root):
        return False
    allowed = []
    for item in allow_bins:
        try:
            allowed.append(item.resolve())
        except OSError:
            continue
    return exe in allowed


def prepare_sandbox_tree(cwd: Path, *, owner_uid: int, game_gid: int) -> None:
    cwd.mkdir(parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(cwd):
        current = Path(dirpath)
        try:
            relative = current.relative_to(cwd)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == ".cyberhost":
            dirnames.clear()
            continue
        os.chown(current, owner_uid, game_gid)
        os.chmod(current, 0o2775)
        for name in filenames:
            path = current / name
            os.chown(path, owner_uid, game_gid)
            os.chmod(path, 0o664)

    control = cwd / ".cyberhost"
    control.mkdir(parents=True, exist_ok=True)
    os.chown(control, owner_uid, game_gid)
    os.chmod(control, 0o750)
    state = control / "state.json"
    if state.exists():
        os.chown(state, owner_uid, owner_uid)
        os.chmod(state, 0o600)
    log = control / "server.log"
    if not log.exists():
        log.touch()
    os.chown(log, owner_uid, game_gid)
    os.chmod(log, 0o660)
