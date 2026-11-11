#!/usr/bin/env python3
"""Compara esquema e contagens entre LAN (.105) e Oracle."""
from __future__ import annotations

import json
import subprocess
import sys

LAN = [
    "ssh", "-i", r"C:\Users\svbul\.ssh\id_ed25519_cyberhost",
    "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
    "rts@192.168.0.105",
    "sudo mariadb -N -B -e \"SELECT table_name FROM information_schema.tables WHERE table_schema='vps_host' AND table_type='BASE TABLE' ORDER BY 1\" vps_host",
]
ORACLE = [
    "ssh", "-i", r"C:\Users\svbul\OneDrive\Desktop\vm oracle\ssh-key-2026-09-01.key",
    "-o", "StrictHostKeyChecking=no",
    "ubuntu@147.15.80.246",
    "sudo mariadb -N -B -e \"SELECT table_name FROM information_schema.tables WHERE table_schema='vps_host' AND table_type='BASE TABLE' ORDER BY 1\" vps_host",
]
COLS_LAN = [
    "ssh", "-i", r"C:\Users\svbul\.ssh\id_ed25519_cyberhost",
    "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
    "rts@192.168.0.105",
    "sudo mariadb -N -B -e \"SELECT CONCAT(table_name,'.',column_name,'|',column_type,'|',is_nullable,'|',IFNULL(column_default,'NULL'),'|',extra) FROM information_schema.columns WHERE table_schema='vps_host' ORDER BY table_name, ordinal_position\" vps_host",
]
COLS_ORACLE = [
    "ssh", "-i", r"C:\Users\svbul\OneDrive\Desktop\vm oracle\ssh-key-2026-09-01.key",
    "-o", "StrictHostKeyChecking=no",
    "ubuntu@147.15.80.246",
    "sudo mariadb -N -B -e \"SELECT CONCAT(table_name,'.',column_name,'|',column_type,'|',is_nullable,'|',IFNULL(column_default,'NULL'),'|',extra) FROM information_schema.columns WHERE table_schema='vps_host' ORDER BY table_name, ordinal_position\" vps_host",
]
COUNTS_LAN = [
    "ssh", "-i", r"C:\Users\svbul\.ssh\id_ed25519_cyberhost",
    "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
    "rts@192.168.0.105",
    "sudo mariadb -N -B -e \"SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema='vps_host' AND table_type='BASE TABLE' ORDER BY 1\" vps_host",
]
COUNTS_ORACLE = [
    "ssh", "-i", r"C:\Users\svbul\OneDrive\Desktop\vm oracle\ssh-key-2026-09-01.key",
    "-o", "StrictHostKeyChecking=no",
    "ubuntu@147.15.80.246",
    "sudo mariadb -N -B -e \"SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema='vps_host' AND table_type='BASE TABLE' ORDER BY 1\" vps_host",
]


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        raise SystemExit(p.returncode)
    return p.stdout.strip()


def lines(raw: str) -> list[str]:
    return [x.strip() for x in raw.splitlines() if x.strip()]


def main() -> None:
    lan_tables = set(lines(run(LAN)))
    ora_tables = set(lines(run(ORACLE)))
    only_lan = sorted(lan_tables - ora_tables)
    only_ora = sorted(ora_tables - lan_tables)
    common = sorted(lan_tables & ora_tables)

    lan_cols = {}
    for row in lines(run(COLS_LAN)):
        table, rest = row.split(".", 1)
        lan_cols.setdefault(table, []).append(rest)

    ora_cols = {}
    for row in lines(run(COLS_ORACLE)):
        table, rest = row.split(".", 1)
        ora_cols.setdefault(table, []).append(rest)

    col_diffs = []
    for table in common:
        lc = lan_cols.get(table, [])
        oc = ora_cols.get(table, [])
        if lc != oc:
            only_lan_cols = [c for c in lc if c not in oc]
            only_ora_cols = [c for c in oc if c not in lc]
            col_diffs.append({
                "table": table,
                "only_lan": only_lan_cols,
                "only_oracle": only_ora_cols,
            })

    lan_counts = {}
    for row in lines(run(COUNTS_LAN)):
        t, n = row.split("\t")
        lan_counts[t] = int(n or 0)
    ora_counts = {}
    for row in lines(run(COUNTS_ORACLE)):
        t, n = row.split("\t")
        ora_counts[t] = int(n or 0)

    report = {
        "lan_tables": len(lan_tables),
        "oracle_tables": len(ora_tables),
        "only_lan": only_lan,
        "only_oracle": only_ora,
        "column_diffs": col_diffs,
        "row_counts": {
            t: {"lan": lan_counts.get(t, 0), "oracle": ora_counts.get(t, 0)}
            for t in sorted(set(lan_counts) | set(ora_counts))
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
