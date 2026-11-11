"""Métricas do host onde o painel roda (servidor em produção). Sem psutil."""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_WHOLE_DISK = re.compile(r"^(sd[a-z]+|vd[a-z]+|hd[a-z]+|nvme\d+n\d+|xvd[a-z]+|mmcblk\d+)$")

_LOCK = threading.Lock()
_PREV: dict | None = None

_SKIP_FS = frozenset(
    {
        "autofs",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "devpts",
        "devtmpfs",
        "efivarfs",
        "fusectl",
        "overlay",
        "proc",
        "pstore",
        "ramfs",
        "rpc_pipefs",
        "securityfs",
        "squashfs",
        "sysfs",
        "tmpfs",
        "tracefs",
        "nsfs",
        "bpf",
        "hugetlbfs",
        "mqueue",
        "binfmt_misc",
    }
)
_SKIP_IFACE_PREFIX = ("lo", "docker", "br-", "veth", "virbr", "tun")


def reset_metrics_state() -> None:
    global _PREV
    with _LOCK:
        _PREV = None


def _read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_cpu_stat(text: str) -> tuple[tuple[int, int], list[tuple[int, int]]]:
    """Retorna ((idle, total), [(idle, total), ...]) por linha cpu/cpuN."""
    overall = (0, 0)
    per: list[tuple[int, int]] = []
    for line in text.splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        if len(parts) < 5:
            continue
        nums = [int(x) for x in parts[1:]]
        user, nice, system, idle = nums[0:4]
        iowait = nums[4] if len(nums) > 4 else 0
        irq = nums[5] if len(nums) > 5 else 0
        softirq = nums[6] if len(nums) > 6 else 0
        steal = nums[7] if len(nums) > 7 else 0
        idle_all = idle + iowait
        total = idle_all + user + nice + system + irq + softirq + steal
        if parts[0] == "cpu":
            overall = (idle_all, total)
        else:
            per.append((idle_all, total))
    return overall, per


def cpu_percent(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float | None:
    if prev is None:
        return None
    d_idle = cur[0] - prev[0]
    d_total = cur[1] - prev[1]
    if d_total <= 0:
        return 0.0
    used = 1.0 - (d_idle / d_total)
    return round(max(0.0, min(100.0, used * 100.0)), 1)


def parse_meminfo(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        num = rest.strip().split()[0]
        try:
            kb = int(num)
        except ValueError:
            continue
        values[key] = kb * 1024
    return values


def parse_netdev(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        fields = rest.split()
        if len(fields) < 16:
            continue
        rows.append(
            {
                "name": name,
                "rx_bytes": int(fields[0]),
                "rx_errors": int(fields[2]),
                "rx_dropped": int(fields[3]),
                "tx_bytes": int(fields[8]),
                "tx_errors": int(fields[10]),
                "tx_dropped": int(fields[11]),
            }
        )
    return rows


def parse_diskstats(text: str) -> tuple[int, int]:
    """Setores lidos/escritos (512 B) de discos reais."""
    read_sectors = 0
    write_sectors = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        name = parts[2]
        if not _WHOLE_DISK.match(name):
            continue
        try:
            read_sectors += int(parts[5])
            write_sectors += int(parts[9])
        except ValueError:
            continue
    return read_sectors, write_sectors


def _os_release_pretty() -> str | None:
    text = _read_text("/etc/os-release")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _uptime_seconds() -> float:
    text = _read_text("/proc/uptime")
    if text:
        try:
            return float(text.split()[0])
        except (IndexError, ValueError):
            pass
    if hasattr(time, "CLOCK_BOOTTIME"):
        try:
            return time.clock_gettime(time.CLOCK_BOOTTIME)
        except OSError:
            pass
    return 0.0


def _loadavg() -> tuple[float | None, float | None, float | None]:
    try:
        a, b, c = os.getloadavg()
        return round(a, 2), round(b, 2), round(c, 2)
    except (OSError, AttributeError):
        return None, None, None


def _linux_mounts() -> list[dict]:
    text = _read_text("/proc/mounts")
    if not text:
        usage = shutil.disk_usage("/")
        return [
            {
                "mount": "/",
                "fstype": "",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0.0,
            }
        ]
    seen_dev: set[str] = set()
    out: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1], parts[2]
        if fstype in _SKIP_FS or mount.startswith("/snap"):
            continue
        if device in seen_dev:
            continue
        if not device.startswith("/dev/") and mount != "/":
            continue
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        seen_dev.add(device)
        percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
        out.append(
            {
                "mount": mount,
                "fstype": fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": percent,
            }
        )
    out.sort(key=lambda row: (row["mount"] != "/", row["mount"]))
    return out


def _temperature_c() -> float | None:
    zone = Path("/sys/class/thermal/thermal_zone0/temp")
    raw = _read_text(zone)
    if not raw:
        return None
    try:
        milli = int(raw.strip())
    except ValueError:
        return None
    if milli > 1000:
        return round(milli / 1000.0, 1)
    return float(milli)


def _process_count() -> int:
    proc = Path("/proc")
    if not proc.is_dir():
        return 0
    n = 0
    for entry in proc.iterdir():
        if entry.name.isdigit():
            n += 1
    return n


def _top_memory(limit: int = 8) -> list[dict]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    rows: list[dict] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        status = _read_text(entry / "status")
        if not status:
            continue
        name = "—"
        rss = 0
        for line in status.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()[:64]
            elif line.startswith("VmRSS:"):
                try:
                    rss = int(line.split()[1]) * 1024
                except (IndexError, ValueError):
                    rss = 0
        if rss <= 0:
            continue
        rows.append({"pid": pid, "name": name, "rss_bytes": rss})
    rows.sort(key=lambda row: row["rss_bytes"], reverse=True)
    return rows[:limit]


def _skip_iface(name: str) -> bool:
    lower = name.lower()
    return any(lower.startswith(prefix) for prefix in _SKIP_IFACE_PREFIX)


def _rate(prev: int | None, cur: int, dt: float) -> float | None:
    if prev is None or dt <= 0:
        return None
    delta = cur - prev
    if delta < 0:
        return 0.0
    return round(delta / dt, 1)


def _windows_memory() -> dict:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise OSError("GlobalMemoryStatusEx failed")
    total = int(stat.ullTotalPhys)
    available = int(stat.ullAvailPhys)
    used = max(0, total - available)
    percent = round((used / total) * 100, 1) if total else 0.0
    swap_total = max(0, int(stat.ullTotalPageFile) - total)
    swap_avail = max(0, int(stat.ullAvailPageFile) - available)
    swap_used = max(0, swap_total - swap_avail)
    swap_percent = round((swap_used / swap_total) * 100, 1) if swap_total else 0.0
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "percent": percent,
        "swap_total_bytes": swap_total,
        "swap_used_bytes": swap_used,
        "swap_percent": swap_percent,
    }


def _windows_cpu_times() -> tuple[int, int] | None:
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    idle = FILETIME()
    kernel = FILETIME()
    user = FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None

    def _quad(ft: FILETIME) -> int:
        return (int(ft.dwHighDateTime) << 32) + int(ft.dwLowDateTime)

    idle_t = _quad(idle)
    kernel_t = _quad(kernel)
    user_t = _quad(user)
    total = kernel_t + user_t
    return idle_t, total


def _windows_disks() -> list[dict]:
    rows: list[dict] = []
    for letter in "CDEFGHIJ":
        root = f"{letter}:\\"
        if not os.path.exists(root):
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
        rows.append(
            {
                "mount": root,
                "fstype": "ntfs",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": percent,
            }
        )
    return rows


def collect_host_metrics() -> dict:
    global _PREV
    now = time.monotonic()
    uname = platform.uname()
    cores = os.cpu_count() or 1
    load_1, load_5, load_15 = _loadavg()

    cpu_overall: tuple[int, int] | None = None
    cpu_per: list[tuple[int, int]] = []
    net_rows: list[dict] = []
    disk_rw: tuple[int, int] | None = None
    memory: dict
    disks: list[dict]
    linux = os.name == "posix" and Path("/proc/stat").is_file()

    if linux:
        stat_text = _read_text("/proc/stat") or ""
        cpu_overall, cpu_per = parse_cpu_stat(stat_text)
        mem = parse_meminfo(_read_text("/proc/meminfo") or "")
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = max(0, total - available)
        swap_total = mem.get("SwapTotal", 0)
        swap_free = mem.get("SwapFree", 0)
        swap_used = max(0, swap_total - swap_free)
        memory = {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "percent": round((used / total) * 100, 1) if total else 0.0,
            "swap_total_bytes": swap_total,
            "swap_used_bytes": swap_used,
            "swap_percent": round((swap_used / swap_total) * 100, 1) if swap_total else 0.0,
        }
        disks = _linux_mounts()
        net_rows = parse_netdev(_read_text("/proc/net/dev") or "")
        disk_rw = parse_diskstats(_read_text("/proc/diskstats") or "")
        uptime = _uptime_seconds()
        processes = _process_count()
        top = _top_memory()
        temp = _temperature_c()
        pretty = _os_release_pretty()
    else:
        memory = _windows_memory()
        disks = _windows_disks()
        cpu_overall = _windows_cpu_times()
        uptime = 0.0
        processes = 0
        top = []
        temp = None
        pretty = f"{uname.system} {uname.release}"

    with _LOCK:
        prev = _PREV
        dt = (now - prev["t"]) if prev else 0.0
        cpu_pct = cpu_percent(prev.get("cpu") if prev else None, cpu_overall) if cpu_overall else None
        per_cpu: list[float] = []
        if cpu_per:
            prev_per = (prev or {}).get("cpu_per") or []
            for idx, cur in enumerate(cpu_per):
                old = prev_per[idx] if idx < len(prev_per) else None
                value = cpu_percent(old, cur)
                per_cpu.append(0.0 if value is None else value)

        prev_net = {row["name"]: row for row in ((prev or {}).get("net") or [])}
        network = []
        for row in net_rows:
            if _skip_iface(row["name"]):
                continue
            old = prev_net.get(row["name"])
            network.append(
                {
                    **row,
                    "rx_bytes_per_sec": _rate(old["rx_bytes"] if old else None, row["rx_bytes"], dt),
                    "tx_bytes_per_sec": _rate(old["tx_bytes"] if old else None, row["tx_bytes"], dt),
                }
            )

        prev_disk = (prev or {}).get("disk_rw")
        read_bps = write_bps = None
        if disk_rw and prev_disk and dt > 0:
            read_bps = max(0.0, (disk_rw[0] - prev_disk[0]) * 512 / dt)
            write_bps = max(0.0, (disk_rw[1] - prev_disk[1]) * 512 / dt)
            read_bps = round(read_bps, 1)
            write_bps = round(write_bps, 1)

        _PREV = {
            "t": now,
            "cpu": cpu_overall,
            "cpu_per": cpu_per,
            "net": net_rows,
            "disk_rw": disk_rw,
        }

    return {
        "collected_at": datetime.now(timezone.utc),
        "hostname": socket.gethostname(),
        "pretty_name": pretty,
        "kernel": f"{uname.system} {uname.release}",
        "architecture": uname.machine or platform.machine(),
        "uptime_seconds": round(uptime, 0),
        "process_count": processes,
        "cpu": {
            "percent": cpu_pct,
            "cores": cores,
            "load_1": load_1,
            "load_5": load_5,
            "load_15": load_15,
            "per_cpu": per_cpu,
        },
        "memory": memory,
        "disks": disks,
        "disk_io": {
            "read_bytes_per_sec": read_bps,
            "write_bytes_per_sec": write_bps,
        },
        "network": network,
        "top_memory": top,
        "temperature_c": temp,
    }
