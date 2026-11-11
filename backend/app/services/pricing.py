"""Cálculo de preços para novos pedidos, upgrades e renovações."""

from __future__ import annotations

from fastapi import HTTPException

from app.models.vps import VpsInstance, VpsPlan, VpsPlanPreset

DEFAULT_DISK_GB = 30


def _marginal_upgrade_delta_cents(
    plan: VpsPlan,
    instance: VpsInstance,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    current_disk_gb: int,
) -> int:
    """Acréscimo mensal por unidade (vCPU/RAM/disco) — usado com mensalidade personalizada."""
    extra_vcpu = max(0, target_vcpu - instance.vcpu)
    extra_ram_gb = max(0, (target_ram_mb - instance.ram_mb) / 1024)
    extra_disk_gb = max(0, target_disk_gb - current_disk_gb)
    return int(
        plan.price_per_vcpu_cents * extra_vcpu
        + plan.price_per_gb_ram_cents * extra_ram_gb
        + plan.price_per_gb_disk_cents * extra_disk_gb
    )


def compute_monthly_price(
    plan: VpsPlan,
    vcpu: int,
    ram_mb: int,
    disk_gb: int,
) -> int:
    """Preço mensal só pelas unidades (vCPU, GB de RAM, GB de disco acima do incluído)."""
    ram_gb = ram_mb / 1024
    extra_disk = max(0, disk_gb - plan.default_disk_gb)
    return int(
        plan.price_per_vcpu_cents * vcpu
        + plan.price_per_gb_ram_cents * ram_gb
        + plan.price_per_gb_disk_cents * extra_disk
    )


def resolve_monthly_price(
    plan: VpsPlan,
    vcpu: int,
    ram_mb: int,
    disk_gb: int,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> int:
    """Preço mensal considerando planos prontos quando as specs coincidem."""
    return calculate_new_order_price(
        plan,
        vcpu,
        ram_mb,
        disk_gb,
        plan_presets=plan_presets or [],
    )


def find_matching_preset(
    presets: list[VpsPlanPreset],
    plan_id: int,
    vcpu: int,
    ram_mb: int,
    disk_gb: int | None = None,
) -> VpsPlanPreset | None:
    _ = disk_gb
    for preset in presets:
        if (
            preset.plan_id == plan_id
            and preset.is_active
            and preset.vcpu == vcpu
            and preset.ram_mb == ram_mb
        ):
            return preset
    return None


def find_floor_preset(
    presets: list[VpsPlanPreset],
    plan_id: int,
    vcpu: int,
    ram_mb: int,
) -> VpsPlanPreset | None:
    """Maior pacote que ainda cabe em vCPU e RAM (desconto de volume)."""
    candidates = [
        preset
        for preset in presets
        if preset.plan_id == plan_id
        and preset.is_active
        and preset.vcpu <= vcpu
        and preset.ram_mb <= ram_mb
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.vcpu + p.ram_mb / 1024, p.price_cents))


def calculate_flexible_price(
    plan: VpsPlan,
    vcpu: int,
    ram_mb: int,
    disk_gb: int,
    *,
    preset: VpsPlanPreset | None = None,
) -> int:
    """
    Preço mensal flexível.
    Com preset: preço do pacote + só o extra de vCPU/RAM/disco.
    Sem preset: tabela unitária do plano.
    """
    if preset:
        price = preset.price_cents
        price += plan.price_per_vcpu_cents * max(0, vcpu - preset.vcpu)
        price += plan.price_per_gb_ram_cents * max(0, ram_mb / 1024 - preset.ram_mb / 1024)
        price += plan.price_per_gb_disk_cents * max(0, disk_gb - preset.disk_gb)
        return int(price)

    return compute_monthly_price(plan, vcpu, ram_mb, disk_gb)


def calculate_new_order_price(
    plan: VpsPlan,
    vcpu: int,
    ram_mb: int,
    disk_gb: int,
    *,
    preset: VpsPlanPreset | None = None,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> int:
    if not preset and plan_presets:
        preset = find_matching_preset(plan_presets, plan.id, vcpu, ram_mb, disk_gb)
        if not preset:
            preset = find_floor_preset(plan_presets, plan.id, vcpu, ram_mb)

    if preset and preset.vcpu == vcpu and preset.ram_mb == ram_mb and preset.disk_gb == disk_gb:
        return preset.price_cents

    return calculate_flexible_price(plan, vcpu, ram_mb, disk_gb, preset=preset)


def classify_upgrade_direction(
    *,
    current_vcpu: int,
    current_ram_mb: int,
    current_disk_gb: int,
    current_network_mbps: int,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    target_network_mbps: int,
) -> str:
    """'upgrade', 'same' ou 'downgrade' — qualquer recurso menor já é downgrade."""
    if (
        target_vcpu < current_vcpu
        or target_ram_mb < current_ram_mb
        or target_disk_gb < current_disk_gb
        or target_network_mbps < current_network_mbps
    ):
        return "downgrade"
    if (
        target_vcpu == current_vcpu
        and target_ram_mb == current_ram_mb
        and target_disk_gb == current_disk_gb
        and target_network_mbps == current_network_mbps
    ):
        return "same"
    return "upgrade"


def prorate_upgrade_amount(instance: VpsInstance, monthly_delta_cents: int) -> dict:
    from app.services.billing import prorate_monthly_delta

    billing_day = instance.paid_until.day if instance.paid_until else instance.billing_day
    proration = prorate_monthly_delta(
        monthly_delta_cents,
        instance.paid_until,
        billing_day,
    )
    return {
        "monthly_delta_cents": monthly_delta_cents,
        "total_cents": proration["amount_cents"],
        **proration,
    }


def calculate_upgrade_monthly_delta(
    plan: VpsPlan,
    instance: VpsInstance,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> int:
    """Acréscimo mensal bruto (sem prorrata) entre configuração atual e alvo."""
    _ = plan_presets
    if target_vcpu < instance.vcpu:
        raise HTTPException(
            status_code=400,
            detail=f"vCPU não pode ser menor que o atual ({instance.vcpu})",
        )
    if target_ram_mb < instance.ram_mb:
        raise HTTPException(
            status_code=400,
            detail=f"RAM não pode ser menor que a atual ({instance.ram_mb // 1024} GB)",
        )
    if target_disk_gb < instance.disk_gb:
        raise HTTPException(
            status_code=400,
            detail=f"Disco não pode ser menor que o atual ({instance.disk_gb} GB)",
        )
    if (
        target_vcpu == instance.vcpu
        and target_ram_mb == instance.ram_mb
        and target_disk_gb == instance.disk_gb
    ):
        raise HTTPException(status_code=400, detail="Nenhum recurso foi alterado")

    disk = instance.disk_gb or plan.default_disk_gb
    # Sempre o acréscimo unitário. Recalcular o plano inteiro (base + preset)
    # fazia 1 GB de RAM pular dezenas de reais.
    return _marginal_upgrade_delta_cents(
        plan, instance, target_vcpu, target_ram_mb, target_disk_gb, disk
    )


def calculate_upgrade_quote(
    plan: VpsPlan,
    instance: VpsInstance,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> dict:
    """Upgrade com prorrata proporcional aos dias até a renovação da VPS."""
    monthly_delta = calculate_upgrade_monthly_delta(
        plan,
        instance,
        target_vcpu,
        target_ram_mb,
        target_disk_gb,
        plan_presets=plan_presets,
    )
    return prorate_upgrade_amount(instance, monthly_delta)


def calculate_upgrade_price(
    plan: VpsPlan,
    instance: VpsInstance,
    target_vcpu: int,
    target_ram_mb: int,
    target_disk_gb: int,
    *,
    plan_presets: list[VpsPlanPreset] | None = None,
) -> int:
    """Upgrade: cobra acréscimo proporcional aos dias até o vencimento."""
    return calculate_upgrade_quote(
        plan,
        instance,
        target_vcpu,
        target_ram_mb,
        target_disk_gb,
        plan_presets=plan_presets,
    )["total_cents"]


def validate_plan_resources(
    plan: VpsPlan,
    vcpu: int,
    ram_mb: int,
    disk_gb: int,
    *,
    min_disk_gb: int | None = None,
) -> None:
    min_disk = max(min_disk_gb or 0, plan.default_disk_gb, DEFAULT_DISK_GB)
    if not (plan.min_vcpu <= vcpu <= plan.max_vcpu):
        raise HTTPException(
            status_code=400,
            detail=f"vCPU deve estar entre {plan.min_vcpu} e {plan.max_vcpu}",
        )
    if not (plan.min_ram_mb <= ram_mb <= plan.max_ram_mb):
        raise HTTPException(
            status_code=400,
            detail=f"RAM deve estar entre {plan.min_ram_mb // 1024} e {plan.max_ram_mb // 1024} GB",
        )
    if not (min_disk <= disk_gb <= plan.max_disk_gb):
        raise HTTPException(
            status_code=400,
            detail=f"Disco deve estar entre {min_disk} e {plan.max_disk_gb} GB",
        )
