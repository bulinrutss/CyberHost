"""Shell interativo do host Linux para administradores (PTY)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from app.config import get_settings

logger = logging.getLogger(__name__)

_SAFE_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TZ")


def shell_available() -> bool:
    settings = get_settings()
    return bool(settings.host_shell_enabled) and sys.platform.startswith("linux")


def build_shell_env(*, cwd: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _SAFE_ENV:
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["TERM"] = "xterm-256color"
    env["SHELL"] = "/bin/bash"
    env["PWD"] = cwd
    if "HOME" not in env:
        env["HOME"] = str(Path.home())
    if "PATH" not in env:
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    return env


def read_pty_chunk(fd: int) -> bytes | None:
    """Lê o PTY sem tratar EAGAIN como desconexão.

    None = sem dados agora; b'' = slave fechou (EOF).
    """
    try:
        return os.read(fd, 8192)
    except BlockingIOError:
        return None
    except InterruptedError:
        return None
    except OSError:
        return b""


def _shell_cwd() -> str:
    settings = get_settings()
    raw = (settings.host_shell_cwd or "").strip() or "/opt/host"
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = Path.home()
    if resolved.is_dir():
        return str(resolved)
    home = Path.home()
    return str(home) if home.is_dir() else "/"


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    import fcntl
    import struct
    import termios

    rows = max(8, min(120, int(rows)))
    cols = max(20, min(400, int(cols)))
    packed = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)
    except OSError:
        logger.debug("host shell winsize ignored")


def _spawn_pty(cwd: str, env: dict[str, str]):
    import pty
    import subprocess

    master, slave = pty.openpty()
    _set_winsize(master, 24, 120)
    proc = subprocess.Popen(
        ["/bin/bash", "-i"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=cwd,
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave)
    return proc, master


async def attach_host_shell(websocket: WebSocket, *, admin_id: int) -> None:
    if not shell_available():
        raise HTTPException(status_code=501, detail="Shell do host disponível só no Linux")

    cwd = _shell_cwd()
    env = build_shell_env(cwd=cwd)
    proc, master = _spawn_pty(cwd, env)
    pid = proc.pid
    logger.info("host shell start admin=%s pid=%s cwd=%s", admin_id, pid, cwd)
    os.set_blocking(master, False)

    loop = asyncio.get_running_loop()
    incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
    send_lock = asyncio.Lock()
    alive = True

    def _on_pty_readable() -> None:
        chunk = read_pty_chunk(master)
        if chunk is None:
            return
        incoming.put_nowait(chunk)

    loop.add_reader(master, _on_pty_readable)

    async def send_bytes(payload: bytes) -> None:
        async with send_lock:
            await websocket.send_bytes(payload)

    async def pump_pty() -> None:
        while True:
            chunk = await incoming.get()
            if chunk is None:
                continue
            if chunk == b"":
                break
            try:
                await send_bytes(chunk)
            except (WebSocketDisconnect, RuntimeError):
                break

    async def pump_ws() -> None:
        nonlocal alive
        try:
            while alive:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                text = message.get("text")
                payload = b""
                if data:
                    payload = data if isinstance(data, (bytes, bytearray)) else bytes(data)
                elif text:
                    if text.startswith("{"):
                        try:
                            body = json.loads(text)
                        except json.JSONDecodeError:
                            payload = text.encode("utf-8", errors="replace")
                        else:
                            if body.get("type") == "resize":
                                _set_winsize(
                                    master,
                                    int(body.get("rows") or 24),
                                    int(body.get("cols") or 80),
                                )
                            continue
                    else:
                        payload = text.encode("utf-8", errors="replace")
                if payload:
                    os.write(master, payload)
        except WebSocketDisconnect:
            pass
        finally:
            alive = False
            incoming.put_nowait(b"")

    try:
        await asyncio.gather(pump_pty(), pump_ws())
    except WebSocketDisconnect:
        incoming.put_nowait(b"")
    except Exception:
        logger.exception("host shell error admin=%s pid=%s", admin_id, pid)
    finally:
        alive = False
        try:
            loop.remove_reader(master)
        except Exception:
            pass
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(pid), signal.SIGHUP)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass
        try:
            os.close(master)
        except OSError:
            pass
        logger.info("host shell stop admin=%s pid=%s", admin_id, pid)
