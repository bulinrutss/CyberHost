"""Isolamento dos sites (cgroup systemd)."""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path

UNIT_PREFIX = "cyberhost-web-"
_UNIT_ID_RE = re.compile(r"^[1-9][0-9]{0,8}$")


def unit_name(site_id: int) -> str:
    if int(site_id) <= 0:
        raise ValueError("site_id inválido")
    return f"{UNIT_PREFIX}{int(site_id)}.service"


def parse_unit_site_id(name: str) -> int:
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


def prepare_sandbox_tree(cwd: Path, *, owner_uid: int, web_gid: int) -> None:
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
        os.chown(current, owner_uid, web_gid)
        os.chmod(current, 0o2775)
        for name in filenames:
            path = current / name
            os.chown(path, owner_uid, web_gid)
            os.chmod(path, 0o664)

    control = cwd / ".cyberhost"
    control.mkdir(parents=True, exist_ok=True)
    os.chown(control, owner_uid, web_gid)
    os.chmod(control, 0o750)
    state = control / "state.json"
    if state.exists():
        os.chown(state, owner_uid, owner_uid)
        os.chmod(state, 0o600)
    log = control / "server.log"
    if not log.exists():
        log.touch()
    os.chown(log, owner_uid, web_gid)
    os.chmod(log, 0o660)


def backend_install_root() -> Path:
    """Raiz do pacote backend (contém app/ e scripts/)."""
    return Path(__file__).resolve().parent.parent.parent


def ensure_web_runtime_visible_to_isolated_user(
    backend_root: Path | None = None,
) -> None:
    """
    Processo isolado (cyberhost-web) precisa traversar backend/scripts e ler
    web_site_server.py. Diretório backend costuma ser 700 (owner rts); sem o+x
    o site estático falha com Permission denied. Idempotente; só roda como root.
    """
    if sys.platform == "win32" or os.geteuid() != 0:
        return
    root = (backend_root or backend_install_root()).resolve()
    scripts = root / "scripts"
    server = scripts / "web_site_server.py"
    for directory in (root, scripts):
        if not directory.is_dir():
            continue
        mode = directory.stat().st_mode
        with_execute = mode | stat.S_IXOTH
        if with_execute != mode:
            os.chmod(directory, with_execute)
    if server.is_file():
        mode = server.stat().st_mode
        with_read = mode | stat.S_IROTH
        if with_read != mode:
            os.chmod(server, with_read)
