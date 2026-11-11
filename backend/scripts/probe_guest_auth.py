"""Probe guest auth on Windows templates. Never prints password values."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyVmomi import vim  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services.os_templates import OS_TEMPLATES  # noqa: E402
from app.services.vmware.client import esxi_session  # noqa: E402
from app.services.vmware.configure import power_on, wait_for_tools  # noqa: E402


def _fp(value: str) -> str:
    if not value:
        return "empty"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _try(auth_mgr, vm, username: str, password: str) -> str:
    auth = vim.NamePasswordAuthentication(
        username=username,
        password=password,
        interactiveSession=False,
    )
    try:
        auth_mgr.ValidateCredentials(vm, auth)
        return "ok"
    except vim.fault.InvalidGuestLogin:
        return "bad_login"
    except vim.fault.GuestOperationsUnavailable:
        return "ops_unavailable"
    except Exception as exc:
        return type(exc).__name__


def main() -> None:
    settings = get_settings()
    sources = {
        "GUEST_ADMIN_PASSWORD": settings.guest_admin_password,
        "GUEST_ADMIN_PASSWORD_SV2012": settings.guest_admin_password_sv2012,
        "GUEST_ADMIN_PASSWORD_SV2016": settings.guest_admin_password_sv2016,
        "GUEST_ADMIN_PASSWORD_SV2019": settings.guest_admin_password_sv2019,
    }
    extra_path = Path("/tmp/ch-extra-pwd")
    if extra_path.is_file():
        for index, extra in enumerate(extra_path.read_text(encoding="utf-8").splitlines(), start=1):
            extra = extra.strip()
            if extra:
                sources[f"extra_{index}"] = extra

    print("user", settings.guest_admin_user)
    for name, value in sources.items():
        print("src", name, "set=" + str(bool(value.strip())), "fp=" + _fp(value.strip()))

    users = []
    for name in (settings.guest_admin_user, "Administrator", "Administrador"):
        if name and name not in users:
            users.append(name)

    unique_passwords: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in sources.items():
        pwd = value.strip()
        if not pwd or pwd in seen:
            continue
        seen.add(pwd)
        unique_passwords.append((name, pwd))

    extra_names = sys.argv[1:]
    targets = [(spec.slug, spec.template_name) for spec in OS_TEMPLATES.values()]
    for name in extra_names:
        targets.append(("clone", name))

    with esxi_session(settings) as client:
        auth_mgr = client.content.guestOperationsManager.authManager
        seen_vm: set[str] = set()
        for slug, vm_name in targets:
            if vm_name in seen_vm:
                continue
            seen_vm.add(vm_name)
            vm = client.find_vm_by_name(vm_name)
            print("---", slug, vm_name)
            if vm is None:
                print("missing")
                continue
            guest = vm.guest
            tools = guest.toolsStatus if guest else None
            host = (guest.hostName or "").strip() if guest else ""
            print(
                "power",
                str(vm.runtime.powerState),
                "tools",
                str(tools),
                "host",
                host or "-",
            )
            if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
                if slug != "clone":
                    print("skip_powered_off")
                    continue
                print("powering_on")
                power_on(client, vm)
                vm = wait_for_tools(client, vm, timeout=420)
                guest = vm.guest
                tools = guest.toolsStatus if guest else None
                host = (guest.hostName or "").strip() if guest else ""
                print("power", str(vm.runtime.powerState), "tools", str(tools), "host", host or "-")
            if not unique_passwords:
                print("no_passwords")
                continue
            any_ok = False
            for src_name, pwd in unique_passwords:
                for user in users:
                    result = _try(auth_mgr, vm, user, pwd)
                    print("try", src_name, "user=" + user, result)
                    if result == "ok":
                        any_ok = True
            print("ok" if any_ok else "FAIL")


if __name__ == "__main__":
    main()
