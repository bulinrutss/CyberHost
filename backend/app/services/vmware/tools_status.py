"""Estado do VMware Tools sem dependência do pyVmomi."""

from __future__ import annotations

TOOLS_MISSING_MESSAGE = (
    "O Windows ainda não está pronto para configuração automática. "
    "A imagem deste sistema precisa do agente de gerenciamento instalado. "
    "Fale com o suporte."
)


def tools_version_int(raw: object) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def is_vmware_tools_missing(guest: object | None) -> bool:
    """True quando a imagem não tem VMware Tools (version 0 / toolsNotInstalled)."""
    if guest is None:
        return False
    version = tools_version_int(getattr(guest, "toolsVersion", 0))
    status = str(getattr(guest, "toolsStatus", "") or "").lower()
    if "notinstalled" in status:
        return True
    return version <= 0 and "toolsok" not in status


def assert_template_has_vmware_tools(vm: object) -> None:
    guest = getattr(vm, "guest", None)
    name = getattr(vm, "name", "?")
    if is_vmware_tools_missing(guest):
        raise RuntimeError(f"Template '{name}': {TOOLS_MISSING_MESSAGE}")
