"""Templates Windows Server e requisitos recomendados por versão."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OsTemplateSlug = Literal["sv2016", "sv2019"]

DEFAULT_OS_TEMPLATE: OsTemplateSlug = "sv2016"

# Rótulo/usuário para VPS já criadas; não aparece na criação.
LEGACY_OS_LABELS = {
    "sv2012": "Windows Server 2012",
}
LEGACY_GUEST_USERNAMES = {
    "sv2012": "Administrador",
}


@dataclass(frozen=True)
class OsTemplateDef:
    slug: OsTemplateSlug
    label: str
    template_name: str
    is_recommended: bool
    recommended_min_vcpu: int
    recommended_min_ram_mb: int
    recommended_min_disk_gb: int
    description: str
    guest_username: str


OS_TEMPLATES: dict[OsTemplateSlug, OsTemplateDef] = {
    "sv2016": OsTemplateDef(
        slug="sv2016",
        label="Windows Server 2016",
        template_name="VPS-BASE-SV2016",
        is_recommended=True,
        recommended_min_vcpu=2,
        recommended_min_ram_mb=2048,
        recommended_min_disk_gb=30,
        description="Versão estável e amplamente compatível.",
        guest_username="Administrator",
    ),
    "sv2019": OsTemplateDef(
        slug="sv2019",
        label="Windows Server 2019",
        template_name="VPS-BASE-SV2019",
        is_recommended=False,
        recommended_min_vcpu=2,
        recommended_min_ram_mb=4096,
        recommended_min_disk_gb=40,
        description="Versão mais recente — exige mais RAM e disco.",
        guest_username="Administrador",
    ),
}


def list_os_templates() -> list[OsTemplateDef]:
    return [OS_TEMPLATES[k] for k in ("sv2016", "sv2019")]


def get_os_template(slug: str) -> OsTemplateDef:
    key = slug.strip().lower()
    if key not in OS_TEMPLATES:
        raise ValueError(f"Sistema operacional inválido: {slug}")
    return OS_TEMPLATES[key]  # type: ignore[index]


def template_name_for_os(slug: str) -> str:
    return get_os_template(slug).template_name


def os_label_for_slug(slug: str | None) -> str | None:
    if not slug:
        return None
    key = slug.strip().lower()
    if key in LEGACY_OS_LABELS:
        return LEGACY_OS_LABELS[key]
    try:
        return get_os_template(key).label
    except ValueError:
        return slug


def guest_username_for_os(slug: str | None) -> str:
    """Usuário local do Windows no template (2016=Administrator, 2019=Administrador)."""
    key = (slug or "").strip().lower()
    if key in LEGACY_GUEST_USERNAMES:
        return LEGACY_GUEST_USERNAMES[key]
    try:
        return get_os_template(key).guest_username
    except ValueError:
        return "Administrator"


def all_template_names() -> set[str]:
    return {t.template_name for t in OS_TEMPLATES.values()}


def spec_warnings(slug: str, *, vcpu: int, ram_mb: int, disk_gb: int) -> list[str]:
    """Avisos não bloqueantes quando a config fica abaixo do recomendado."""
    try:
        spec = get_os_template(slug)
    except ValueError:
        return []

    warnings: list[str] = []
    if vcpu < spec.recommended_min_vcpu:
        warnings.append(
            f"{spec.label}: recomendamos pelo menos {spec.recommended_min_vcpu} vCPU "
            f"(selecionado: {vcpu})."
        )
    ram_gb = ram_mb / 1024
    min_ram_gb = spec.recommended_min_ram_mb / 1024
    if ram_mb < spec.recommended_min_ram_mb:
        warnings.append(
            f"{spec.label}: recomendamos pelo menos {min_ram_gb:g} GB de RAM "
            f"(selecionado: {ram_gb:g} GB)."
        )
    if disk_gb < spec.recommended_min_disk_gb:
        warnings.append(
            f"{spec.label}: recomendamos pelo menos {spec.recommended_min_disk_gb} GB de disco "
            f"(selecionado: {disk_gb} GB)."
        )
    return warnings
