#!/usr/bin/env python3
from pathlib import Path

import paramiko

NAMES = [
    "br.png",
    "dayz.png",
    "favicon.ico",
    "fivem.webp",
    "logo2.png",
    "logo3.png",
    "mine.webp",
    "mtasa.webp",
    "rust.png",
    "server.png",
]

dest = Path(__file__).resolve().parents[1] / "frontend" / "public"
dest.mkdir(parents=True, exist_ok=True)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.105", username="rts", password=__import__("os").environ.get("CYBERHOST_SSH_PASSWORD"), timeout=15)
sftp = c.open_sftp()
for name in NAMES:
    remote = f"/opt/host/frontend/public/cyberhost/{name}"
    local = dest / name
    sftp.get(remote, str(local))
    print("downloaded", name)
sftp.close()
c.close()
