#!/usr/bin/env python3
"""Root helper: inicia/para o site isolado (UID + cgroup)."""

from __future__ import annotations

import argparse
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.web_sandbox import (  # noqa: E402
    ensure_web_runtime_visible_to_isolated_user,
    is_allowed_executable,
    is_safe_cwd,
    is_under_root,
    parse_unit_site_id,
    prepare_sandbox_tree,
    unit_name,
)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("web_process_spawn.py deve rodar como root")


def _lookup(user: str) -> pwd.struct_passwd:
    try:
        return pwd.getpwnam(user)
    except KeyError as exc:
        raise SystemExit(f"usuário {user} inexistente") from exc


def _stop_unit(unit: str) -> None:
    parse_unit_site_id(unit)
    subprocess.run(["/bin/systemctl", "stop", unit], check=False, capture_output=True)
    subprocess.run(["/bin/systemctl", "reset-failed", unit], check=False, capture_output=True)


def _main_pid(unit: str, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["/bin/systemctl", "show", "-p", "MainPID", "--value", unit],
            check=False,
            capture_output=True,
            text=True,
        )
        pid = (result.stdout or "").strip()
        if pid.isdigit() and int(pid) > 1:
            return int(pid)
        time.sleep(0.1)
    raise SystemExit(f"MainPID indisponível para {unit}")


def spawn(args: argparse.Namespace) -> int:
    _require_root()
    ensure_web_runtime_visible_to_isolated_user()
    unit = unit_name(args.site_id)
    owner = _lookup(args.owner)
    web = _lookup(args.user)
    data_root = Path(args.data_root)
    cwd = Path(args.cwd)
    log_path = Path(args.log)
    command = list(args.command)
    if not command:
        raise SystemExit("comando vazio")
    if not is_safe_cwd(cwd, data_root):
        raise SystemExit("cwd fora do data root")
    exe = Path(command[0])
    if not exe.is_absolute():
        raise SystemExit("binário deve ser caminho absoluto")
    allow = [Path(item) for item in args.allow_bin]
    if not is_allowed_executable(exe, data_root, allow):
        raise SystemExit("binário não permitido")
    if not log_path.is_absolute() or not is_under_root(log_path, cwd):
        raise SystemExit("log fora do diretório do site")

    prepare_sandbox_tree(cwd, owner_uid=owner.pw_uid, web_gid=web.pw_gid)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()
    os.chown(log_path, owner.pw_uid, web.pw_gid)
    os.chmod(log_path, 0o660)

    memory_mb = max(64, int(args.memory_mb))
    cpu_quota = max(5, min(100, int(args.cpu_quota)))
    tasks_max = max(8, min(256, int(args.tasks_max)))

    _stop_unit(unit)
    result = subprocess.run(
        [
            "/usr/bin/systemd-run",
            f"--unit={unit.removesuffix('.service')}",
            f"--uid={web.pw_name}",
            f"--gid={web.pw_name}",
            f"--working-directory={cwd}",
            f"--property=MemoryMax={memory_mb}M",
            "--property=MemorySwapMax=0",
            f"--property=CPUQuota={cpu_quota}%",
            f"--property=TasksMax={tasks_max}",
            "--property=LimitCORE=0",
            "--property=NoNewPrivileges=yes",
            "--property=PrivateTmp=yes",
            "--property=ProtectHome=yes",
            "--property=RestrictSUIDSGID=yes",
            "--property=LockPersonality=yes",
            "--property=IPAddressAllow=127.0.0.1",
            "--property=IPAddressDeny=any",
            "--property=UMask=002",
            f"--property=StandardOutput=append:{log_path}",
            "--property=StandardError=inherit",
            "--collect",
            "--service-type=exec",
            "--quiet",
            "--",
            *command,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "systemd-run falhou").strip()
        raise SystemExit(err[:500])
    pid = _main_pid(unit)
    print(pid)
    return 0


def stop(args: argparse.Namespace) -> int:
    _require_root()
    _stop_unit(unit_name(args.site_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="web_process_spawn")
    sub = parser.add_subparsers(dest="action", required=True)
    spawn_p = sub.add_parser("spawn")
    spawn_p.add_argument("--site-id", type=int, required=True)
    spawn_p.add_argument("--user", required=True)
    spawn_p.add_argument("--owner", required=True)
    spawn_p.add_argument("--data-root", required=True)
    spawn_p.add_argument("--cwd", required=True)
    spawn_p.add_argument("--log", required=True)
    spawn_p.add_argument("--memory-mb", type=int, default=256)
    spawn_p.add_argument("--cpu-quota", type=int, default=25)
    spawn_p.add_argument("--tasks-max", type=int, default=64)
    spawn_p.add_argument("--allow-bin", action="append", default=[])
    spawn_p.add_argument("command", nargs=argparse.REMAINDER)
    spawn_p.set_defaults(func=spawn)
    stop_p = sub.add_parser("stop")
    stop_p.add_argument("--site-id", type=int, required=True)
    stop_p.set_defaults(func=stop)
    args = parser.parse_args(argv)
    if args.action == "spawn" and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
