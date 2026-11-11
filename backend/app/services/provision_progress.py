"""Atualização de progresso do provisionamento para o cliente."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.vps import VpsOrder

_VENDOR_COPY_RE = re.compile(r"vmware(?:\s+tools)?|\besxi\b", re.I)
CUSTOMER_GENERIC_ERROR = (
    "Não foi possível concluir a configuração automática. "
    "Tente novamente ou fale com o suporte."
)


def sanitize_customer_error(message: str | None) -> str | None:
    """Remove menções a VMware/ESXi de erros já gravados no banco."""
    if not message:
        return None
    if _VENDOR_COPY_RE.search(message):
        return CUSTOMER_GENERIC_ERROR
    return message

STEP_LABELS: dict[str, str] = {
    "payment_pending": "Aguardando pagamento",
    "payment_confirmed": "Pagamento confirmado",
    "preparing": "Preparando servidor",
    "copying_disk": "Copiando disco do template",
    "registering": "Registrando servidor",
    "configuring": "Configurando CPU e RAM",
    "powering_off": "Desligando servidor",
    "powering_on": "Ligando servidor",
    "starting_os": "Inicializando Windows",
    "waiting_tools": "Aguardando o Windows iniciar",
    "waiting_auth": "Autenticando no Windows",
    "configuring_network": "Configurando rede",
    "extending_disk": "Expandindo disco",
    "rearming_windows": "Resetando prazo de ativação Windows",
    "rebooting": "Reiniciando para aplicar rearm",
    "applying_upgrade": "Aplicando upgrade",
    "admin_applied": "Alteração aplicada",
    "ready": "Servidor pronto",
    "failed": "Falha no provisionamento",
}


def update_order_progress(
    db: Session,
    order: VpsOrder,
    *,
    progress: int,
    step: str,
) -> None:
    order.provision_progress = min(100, max(0, progress))
    order.provision_step = step
    db.commit()


def disk_copy_progress(vmware_percent: int) -> int:
    """Mapeia progresso da cópia do disco (0–100) para 15–60% do fluxo total."""
    return 15 + int(vmware_percent * 0.45)


def provision_fields_for_instance(instance) -> dict:
    """Campos de progresso para listagem/detalhe da VPS."""
    from app.models.vps import OrderStatus, VpsStatus

    order = getattr(instance, "order", None)
    is_provisioning = instance.status in (
        VpsStatus.CREATING,
        VpsStatus.CONFIGURING,
    ) or (order is not None and order.status in (OrderStatus.PAID, OrderStatus.PROVISIONING))

    if not is_provisioning:
        return {
            "is_provisioning": False,
            "provision_progress": None,
            "provision_label": None,
        }

    progress = order.provision_progress if order else 0
    label = None
    if order and order.provision_step:
        label = STEP_LABELS.get(order.provision_step, order.provision_step)

    return {
        "is_provisioning": True,
        "provision_progress": progress,
        "provision_label": label,
    }
