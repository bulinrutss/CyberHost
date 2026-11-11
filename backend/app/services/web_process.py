"""Processo HTTP do site (systemd-run no Linux, Popen no Windows)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config import Settings, get_settings
from app.models.web_site import WebSite, WebSiteStatus
from app.services.web_sandbox import is_allowed_executable, is_under_root, unit_name

logger = logging.getLogger(__name__)

STATE_FILE = ".cyberhost/state.json"
LOG_FILE = ".cyberhost/server.log"
LOG_TAIL_MAX_LINES = 500
LOG_TAIL_MAX_BYTES = 256 * 1024


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
        settings.web_process_isolate
        and sys.platform != "win32"
        and settings.web_process_user.strip()
    )


def _spawn_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts" / "web_process_spawn.py"


def _server_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts" / "web_site_server.py"


def _data_root(settings: Settings) -> Path:
    root = Path(settings.web_sites_data_path)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _public_dir(data_path: str) -> Path:
    path = Path(data_path) / "public"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _php_bin(settings: Settings) -> Path | None:
    raw = (settings.web_php_binary or "").strip() or "php"
    path = Path(raw)
    if not path.is_absolute():
        found = shutil.which(raw)
        if not found:
            return None
        path = Path(found)
    return path if path.is_file() else None


def _runtime_python(settings: Settings) -> Path:
    """Python acessível ao usuário isolado (venv costuma apontar para $HOME)."""
    if isolation_enabled(settings):
        for candidate in ("/usr/bin/python3", "/usr/bin/python"):
            path = Path(candidate)
            if path.is_file():
                return path
        found = shutil.which("python3")
        if found:
            return Path(found)
    return Path(sys.executable).resolve()


def _allow_bins(settings: Settings) -> list[Path]:
    bins = [_runtime_python(settings)]
    php = _php_bin(settings)
    if php:
        bins.append(php)
    return bins


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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


def _site_command(site: WebSite, settings: Settings) -> list[str]:
    public = str(_public_dir(site.data_path))
    php = _php_bin(settings) if site.php_enabled else None
    if php:
        return [str(php.resolve()), "-S", f"127.0.0.1:{site.port}", "-t", public]
    script = _server_script().resolve()
    return [
        str(_runtime_python(settings)),
        str(script),
        "--bind",
        "127.0.0.1",
        "--port",
        str(site.port),
        "--root",
        public,
    ]


def sync_site_status(site: WebSite) -> WebSite:
    pid = site.process_pid or _read_state(site.data_path).get("pid")
    running = _is_pid_running(int(pid)) if pid else False
    if running:
        site.status = WebSiteStatus.RUNNING
        site.process_pid = int(pid)
    elif site.status in (WebSiteStatus.RUNNING, WebSiteStatus.STARTING, WebSiteStatus.STOPPING):
        site.status = WebSiteStatus.STOPPED
        site.process_pid = None
    return site


def start_site(site: WebSite, settings: Settings | None = None) -> WebSite:
    settings = settings or get_settings()
    if site.suspended_for_billing:
        raise RuntimeError("Site suspenso por inadimplência")
    cwd = Path(site.data_path)
    cwd.mkdir(parents=True, exist_ok=True)
    _public_dir(site.data_path)
    log = _log_path(site.data_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.touch()
    command = _site_command(site, settings)
    exe = Path(command[0])
    if isolation_enabled(settings):
        if not is_allowed_executable(exe, _data_root(settings), _allow_bins(settings)):
            raise RuntimeError("Binário do site não permitido")
        cmd = [
            "sudo",
            "-n",
            sys.executable,
            str(_spawn_script()),
            "spawn",
            "--site-id",
            str(site.id),
            "--user",
            settings.web_process_user,
            "--owner",
            settings.web_process_owner,
            "--data-root",
            str(_data_root(settings)),
            "--cwd",
            str(cwd.resolve()),
            "--log",
            str(log.resolve()),
            "--memory-mb",
            str(site.ram_mb),
            "--cpu-quota",
            str(site.cpu_percent),
            "--tasks-max",
            str(settings.web_process_tasks_max),
        ]
        for item in _allow_bins(settings):
            cmd.extend(["--allow-bin", str(item)])
        cmd.append("--")
        cmd.extend(command)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "falha ao iniciar").strip()
            raise RuntimeError(err[:500])
        pid = int((result.stdout or "").strip().splitlines()[-1])
    else:
        if isolation_enabled(settings) is False and sys.platform != "win32":
            pass
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log.open("ab"),
            stderr=subprocess.STDOUT,
        )
        pid = proc.pid
        time.sleep(0.2)
        if proc.poll() is not None:
            raise RuntimeError("Processo do site encerrou na hora")
    site.process_pid = pid
    site.status = WebSiteStatus.RUNNING
    site.error_message = None
    _write_state(site.data_path, {"pid": pid, "unit": unit_name(site.id)})
    return site


def stop_site(site: WebSite, settings: Settings | None = None) -> WebSite:
    settings = settings or get_settings()
    if isolation_enabled(settings):
        subprocess.run(
            [
                "sudo",
                "-n",
                sys.executable,
                str(_spawn_script()),
                "stop",
                "--site-id",
                str(site.id),
            ],
            check=False,
            capture_output=True,
        )
    pid = site.process_pid or _read_state(site.data_path).get("pid")
    if pid and _is_pid_running(int(pid)) and sys.platform == "win32":
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
    elif pid and _is_pid_running(int(pid)) and not isolation_enabled(settings):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
    site.process_pid = None
    site.status = WebSiteStatus.STOPPED
    _write_state(site.data_path, {})
    return site


def _purge_site_data(site: WebSite, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    raw = (site.data_path or "").strip()
    if not raw:
        return
    data = Path(raw).resolve()
    root = Path(settings.web_sites_data_path).resolve()
    if is_under_root(data, root):
        shutil.rmtree(data, ignore_errors=True)


def destroy_site(site: WebSite, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if site.status == WebSiteStatus.DELETED:
        return "Site já estava apagado"
    slug = site.site_slug
    try:
        stop_site(site, settings)
    except Exception as exc:
        logger.warning("Falha ao parar site id=%s (%s)", site.id, type(exc).__name__)
    try:
        from app.services.web_nginx import reload_nginx, remove_snippet

        remove_snippet(site, settings)
        reload_nginx(settings)
    except Exception as exc:
        logger.warning("Falha ao remover nginx site id=%s (%s)", site.id, type(exc).__name__)
    try:
        from app.services.web_ssl import release_certificate_for_site

        release_certificate_for_site(site.id)
    except Exception as exc:
        logger.warning("Falha ao remover certificado SSL site id=%s (%s)", site.id, type(exc).__name__)
    _purge_site_data(site, settings)
    if site.order_id:
        from sqlalchemy.orm import object_session

        from app.models.web_site import WebOrder

        session = object_session(site)
        if session is not None:
            order = session.get(WebOrder, site.order_id)
            if order is not None:
                order.domain = None
    site.domain = None
    site.process_pid = None
    site.status = WebSiteStatus.DELETED
    site.error_message = None
    return f"Site {slug} apagado"


def tail_logs(data_path: str, lines: int = 100) -> str:
    path = _log_path(data_path)
    if not path.is_file():
        return ""
    max_lines = max(1, min(int(lines), LOG_TAIL_MAX_LINES))
    try:
        data = path.read_bytes()[-LOG_TAIL_MAX_BYTES:]
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-max_lines:])
