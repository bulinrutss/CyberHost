"""Controle de processos dos servidores de jogo (local ou com binário real)."""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.config import Settings, get_settings
from app.models.game_server import GameServer, GameServerStatus, GameType
from app.services.game_sandbox import UNIT_PREFIX, is_allowed_executable, unit_name

logger = logging.getLogger(__name__)

STATE_FILE = ".cyberhost/state.json"
LOG_FILE = ".cyberhost/server.log"
LOG_TAIL_MAX_LINES = 500
LOG_TAIL_MAX_BYTES = 256 * 1024
LOG_TAIL_CHUNK_BYTES = 8192
LOG_ROTATE_MAX_BYTES = 8 * 1024 * 1024
LOG_ROTATE_KEEP = 3


def _state_path(data_path: str) -> Path:
    return Path(data_path) / STATE_FILE


def _log_path(data_path: str) -> Path:
    return Path(data_path) / LOG_FILE


def _read_state(data_path: str) -> dict:
    path = _state_path(data_path)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(data_path: str, state: dict) -> None:
    path = _state_path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def isolation_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.game_process_isolate
        and sys.platform != "win32"
        and settings.game_process_user.strip()
    )


def _spawn_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts" / "game_process_spawn.py"


def _absolute_command(command: list[str], *, cwd: Path) -> list[str]:
    if not command:
        return command
    resolved = _expected_executable(command, cwd=cwd)
    if resolved is None:
        raise RuntimeError("Binário do servidor de jogo não encontrado")
    return [str(resolved), *command[1:]]


def _allow_bins(settings: Settings) -> list[Path]:
    bins: list[Path] = []
    for raw in (
        settings.game_samp_binary,
        settings.game_mta_binary,
        settings.game_fivem_binary,
        settings.game_minecraft_java or "java",
        sys.executable,
    ):
        text = (raw or "").strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_absolute():
            found = shutil.which(text)
            if found:
                path = Path(found)
        if path.exists():
            bins.append(path)
    stub = _stub_script_path()
    if stub.exists():
        bins.append(Path(sys.executable))
    return bins


def _data_root(settings: Settings) -> Path:
    root = Path(settings.game_servers_data_path)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _proc_real_uid(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _proc_cgroup_unit(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except OSError:
        return None
    expected_prefix = UNIT_PREFIX
    for chunk in text.replace("\n", "/").split("/"):
        if chunk.startswith(expected_prefix) and chunk.endswith(".service"):
            return chunk
    return None


def _sudo_python_cmd(*extra: str) -> list[str]:
    return ["sudo", "-n", sys.executable, str(_spawn_script()), *extra]


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _expected_executable(command: list[str], *, cwd: Path) -> Path | None:
    if not command:
        return None
    raw = Path(command[0])
    if raw.is_absolute():
        return raw.resolve()
    resolved = shutil.which(command[0])
    if resolved:
        return Path(resolved).resolve()
    candidate = (cwd / raw).resolve()
    return candidate if candidate.exists() else None


def _windows_process_executable(pid: int) -> Path | None:
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = ctypes.c_ulong(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return None
            return Path(buffer.value).resolve()
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return None


def _is_managed_process(
    server: GameServer,
    pid: int,
    settings: Settings | None = None,
) -> bool:
    """Confirma que o PID ainda é o processo iniciado para este servidor."""
    if not _is_pid_running(pid):
        return False
    settings = settings or get_settings()
    if isolation_enabled(settings):
        try:
            if _is_isolated_process(server, pid, settings):
                return True
        except RuntimeError:
            pass
    data = Path(server.data_path).resolve()
    expected_command = _build_start_command(server, settings, log_path=_log_path(server.data_path))
    expected_executable = _expected_executable(expected_command, cwd=data)
    if expected_executable is None:
        return False

    if sys.platform == "win32":
        actual_executable = _windows_process_executable(pid)
        return actual_executable == expected_executable

    proc = Path("/proc") / str(pid)
    try:
        actual_cwd = (proc / "cwd").resolve(strict=True)
        actual_executable = (proc / "exe").resolve(strict=True)
        session_leader = os.getsid(pid) == pid
    except (OSError, RuntimeError):
        return False
    return (
        actual_cwd == data
        and actual_executable == expected_executable
        and session_leader
    )


def _is_isolated_process(server: GameServer, pid: int, settings: Settings) -> bool:
    if not _is_pid_running(pid):
        return False
    data = Path(server.data_path).resolve()
    expected_command = _absolute_command(
        _build_start_command(server, settings, log_path=_log_path(server.data_path)),
        cwd=data,
    )
    expected_executable = _expected_executable(expected_command, cwd=data)
    if expected_executable is None:
        return False
    proc = Path("/proc") / str(pid)
    try:
        actual_cwd = (proc / "cwd").resolve(strict=True)
        actual_executable = (proc / "exe").resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if actual_cwd != data or actual_executable != expected_executable:
        return False
    if _proc_cgroup_unit(pid) != unit_name(server.id):
        return False
    try:
        import pwd

        expected_uid = pwd.getpwnam(settings.game_process_user.strip()).pw_uid
    except KeyError:
        return False
    return _proc_real_uid(pid) == expected_uid


def _stub_script_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts" / "game_server_stub.py"


def _build_start_command(
    server: GameServer,
    settings: Settings,
    *,
    log_path: Path,
) -> list[str]:
    game = server.game_type.value if isinstance(server.game_type, GameType) else str(server.game_type)
    data = Path(server.data_path)

    if game == GameType.SAMP.value and settings.game_samp_binary:
        return [settings.game_samp_binary, "-n", "-H", str(server.port), "-m", str(server.slots)]

    if game == GameType.MTA.value and settings.game_mta_binary:
        return [settings.game_mta_binary, str(data / "mods" / "deathmatch" / "mtaserver.conf")]

    if game == GameType.MINECRAFT.value and settings.game_minecraft_jar:
        java = settings.game_minecraft_java or "java"
        return [
            java,
            f"-Xmx{server.ram_mb}M",
            f"-Xms{min(server.ram_mb, 1024)}M",
            "-jar",
            settings.game_minecraft_jar,
            "nogui",
        ]

    if game == GameType.FIVEM.value and settings.game_fivem_binary:
        return [settings.game_fivem_binary, "+exec", "server.cfg"]

    stub = _stub_script_path()
    return [
        sys.executable,
        str(stub),
        "--game",
        game,
        "--port",
        str(server.port),
        "--name",
        server.server_name,
        "--slots",
        str(server.slots),
    ]


def sync_server_status(server: GameServer) -> GameServerStatus:
    """Atualiza status usando somente o PID confiável salvo no banco."""
    pid = server.process_pid
    if pid and _is_managed_process(server, int(pid)):
        return GameServerStatus.RUNNING
    if pid and _is_pid_running(int(pid)):
        logger.error(
            "PID %s do servidor %s não pertence ao processo gerenciado; ignorando",
            pid,
            server.id,
        )
    if server.status in (GameServerStatus.STARTING, GameServerStatus.RUNNING):
        return GameServerStatus.STOPPED
    return server.status


def _isolated_spawn_argv(
    server: GameServer,
    settings: Settings,
    command: list[str],
    log_path: Path,
) -> list[str]:
    argv = _sudo_python_cmd(
        "spawn",
        "--server-id",
        str(int(server.id)),
        "--user",
        settings.game_process_user.strip(),
        "--owner",
        settings.game_process_owner.strip() or "rts",
        "--memory-mb",
        str(max(128, int(server.ram_mb) + 256)),
        "--cpu-quota",
        str(max(10, min(400, int(settings.game_process_cpu_quota_percent)))),
        "--tasks-max",
        str(max(8, min(512, int(settings.game_process_tasks_max)))),
        "--data-root",
        str(_data_root(settings)),
        "--cwd",
        str(Path(server.data_path).resolve()),
        "--log",
        str(log_path.resolve()),
    )
    for item in _allow_bins(settings):
        argv.extend(["--allow-bin", str(item)])
    argv.append("--")
    argv.extend(command)
    return argv


def _spawn_isolated(
    server: GameServer,
    settings: Settings,
    command: list[str],
    log_path: Path,
) -> int:
    result = subprocess.run(
        _isolated_spawn_argv(server, settings, command, log_path),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "falha ao isolar processo").strip()
        raise RuntimeError(err[:300])
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if not lines or not lines[-1].isdigit():
        raise RuntimeError("spawn isolado não retornou PID")
    return int(lines[-1])


def _stop_isolated(server: GameServer) -> None:
    result = subprocess.run(
        _sudo_python_cmd("stop", "--server-id", str(int(server.id))),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "Falha ao parar unit isolada do servidor %s: %s",
            server.id,
            (result.stderr or result.stdout or "")[:200],
        )


def start_server(server: GameServer, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    data = Path(server.data_path).resolve()
    data.mkdir(parents=True, exist_ok=True)
    log_path = _log_path(str(data))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotate_game_log(log_path)

    pid = server.process_pid
    if pid and _is_managed_process(server, int(pid), settings):
        return int(pid)
    if pid and _is_pid_running(int(pid)):
        raise RuntimeError(
            "PID registrado não pertence a este servidor; início recusado por segurança"
        )

    cmd = _absolute_command(
        _build_start_command(server, settings, log_path=log_path),
        cwd=data,
    )
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    if isolation_enabled(settings):
        if not is_allowed_executable(Path(cmd[0]), _data_root(settings), _allow_bins(settings)):
            raise RuntimeError("Binário não permitido para isolamento")
        new_pid = _spawn_isolated(server, settings, cmd, log_path)
    else:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        log_file = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(data),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=sys.platform != "win32",
        )
        log_file.close()
        new_pid = proc.pid

    _write_state(
        str(data),
        {
            "pid": new_pid,
            "game_type": server.game_type.value if isinstance(server.game_type, GameType) else server.game_type,
            "port": server.port,
            "started_at": time.time(),
            "command": cmd,
        },
    )
    logger.info("Servidor de jogo %s iniciado PID=%s porta=%s", server.id, new_pid, server.port)
    return new_pid


def stop_server(server: GameServer, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    pid = server.process_pid
    if not pid:
        _write_state(server.data_path, {"pid": None})
        return

    pid = int(pid)
    if not _is_pid_running(pid):
        if isolation_enabled(settings):
            _stop_isolated(server)
        _write_state(server.data_path, {"pid": None})
        return
    if not _is_managed_process(server, pid, settings):
        logger.error(
            "Recusando encerrar PID %s do servidor %s: identidade do processo não confere",
            pid,
            server.id,
        )
        _write_state(server.data_path, {"pid": None})
        return

    try:
        if isolation_enabled(settings) and _proc_cgroup_unit(pid) == unit_name(server.id):
            _stop_isolated(server)
        elif sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not _is_pid_running(pid):
                    break
                time.sleep(0.25)
            if _is_managed_process(server, pid, settings):
                os.kill(pid, signal.SIGKILL)
    except Exception as exc:
        logger.warning("Erro ao parar PID %s: %s", pid, exc)

    log_path = _log_path(server.data_path)
    if log_path.is_file():
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- stop {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    _write_state(server.data_path, {"pid": None})
    logger.info("Servidor de jogo %s parado (PID=%s)", server.id, pid)


def restart_server(server: GameServer, settings: Settings | None = None) -> int:
    stop_server(server, settings)
    time.sleep(0.5)
    return start_server(server, settings)


def _rotated_log_path(path: Path, generation: int) -> Path:
    return path.with_name(f"{path.name}.{generation}")


def rotate_game_log(
    path: Path,
    *,
    max_bytes: int | None = None,
    keep: int | None = None,
) -> bool:
    """Copia e trunca o log ativo se passar do teto (o processo pode manter o mesmo fd)."""
    max_bytes = LOG_ROTATE_MAX_BYTES if max_bytes is None else max_bytes
    keep = LOG_ROTATE_KEEP if keep is None else keep
    if max_bytes < 1 or keep < 1:
        return False
    try:
        if not path.is_file() or path.stat().st_size < max_bytes:
            return False
    except OSError:
        return False

    for generation in range(keep, 1, -1):
        src = _rotated_log_path(path, generation - 1)
        dst = _rotated_log_path(path, generation)
        try:
            if dst.exists():
                dst.unlink()
            if src.exists():
                src.replace(dst)
        except OSError:
            logger.warning("Falha ao rotacionar %s", dst.name, exc_info=True)
            return False

    backup = _rotated_log_path(path, 1)
    try:
        if backup.exists():
            backup.unlink()
        shutil.copy2(path, backup)
        with path.open("r+b") as handle:
            handle.truncate(0)
    except OSError:
        logger.warning("Falha ao truncar log de game %s", path, exc_info=True)
        return False
    logger.info("Log de game rotacionado %s (%s gerações)", path.name, keep)
    return True


def _tail_bytes(path: Path, *, max_lines: int, max_bytes: int, chunk: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size <= 0:
            return b""
        remaining_budget = min(size, max_bytes)
        pos = size
        parts: list[bytes] = []
        newlines = 0
        while remaining_budget > 0 and pos > 0:
            step = min(chunk, remaining_budget, pos)
            pos -= step
            handle.seek(pos)
            block = handle.read(step)
            parts.append(block)
            remaining_budget -= step
            newlines += block.count(b"\n")
            if newlines >= max_lines:
                break
        data = b"".join(reversed(parts))
        if pos > 0:
            cut = data.find(b"\n")
            if cut != -1:
                data = data[cut + 1 :]
        return data


def tail_logs(data_path: str, lines: int = 100) -> str:
    path = _log_path(data_path)
    if not path.is_file():
        return ""
    max_lines = max(1, min(int(lines), LOG_TAIL_MAX_LINES))
    try:
        data = _tail_bytes(
            path,
            max_lines=max_lines,
            max_bytes=LOG_TAIL_MAX_BYTES,
            chunk=LOG_TAIL_CHUNK_BYTES,
        )
    except OSError:
        return ""
    rotate_game_log(path)
    text = data.decode("utf-8", errors="replace")
    all_lines = text.splitlines()
    return "\n".join(all_lines[-max_lines:])
