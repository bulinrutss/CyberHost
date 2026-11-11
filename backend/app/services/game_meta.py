"""Metadados e portas padrão por tipo de jogo."""

from __future__ import annotations

from app.models.game_server import GameType

GAME_TYPE_LABELS: dict[str, str] = {
    GameType.SAMP.value: "SA-MP",
    GameType.MTA.value: "MTA:SA",
    GameType.MINECRAFT.value: "Minecraft",
    GameType.FIVEM.value: "FiveM",
}

GAME_TYPE_DESCRIPTIONS: dict[str, str] = {
    GameType.SAMP.value: (
        "San Andreas Multiplayer — painel com arquivos do servidor, "
        "start/stop e edição de server.cfg."
    ),
    GameType.MTA.value: (
        "Multi Theft Auto — hospedagem leve com recursos Lua, "
        "mtaserver.conf e scripts no painel."
    ),
    GameType.MINECRAFT.value: (
        "Minecraft Java — servidor Paper/Spigot com plugins, "
        "server.properties e console no painel."
    ),
    GameType.FIVEM.value: (
        "FiveM (GTA V) — FXServer com resources, server.cfg e "
        "start/stop no painel. Requer host Linux."
    ),
}

DEFAULT_PORTS: dict[str, int] = {
    GameType.SAMP.value: 7777,
    GameType.MTA.value: 22003,
    GameType.MINECRAFT.value: 25565,
    GameType.FIVEM.value: 30120,
}

PORT_RANGES: dict[str, tuple[int, int]] = {
    GameType.SAMP.value: (7777, 7999),
    GameType.MTA.value: (22003, 22999),
    GameType.MINECRAFT.value: (25565, 25999),
    GameType.FIVEM.value: (30120, 30299),
}

CONFIG_FILES: dict[str, str] = {
    GameType.SAMP.value: "server.cfg",
    GameType.MTA.value: "mods/deathmatch/mtaserver.conf",
    GameType.MINECRAFT.value: "server.properties",
    GameType.FIVEM.value: "server.cfg",
}

PROVISION_STEP_LABELS: dict[str, str] = {
    "payment_pending": "Aguardando pagamento",
    "payment_confirmed": "Pagamento confirmado",
    "allocating_port": "Alocando porta",
    "deploying_files": "Preparando arquivos",
    "configuring": "Configurando servidor",
    "ready": "Servidor pronto",
    "failed": "Falha no provisionamento",
}


def game_type_label(game_type: str) -> str:
    return GAME_TYPE_LABELS.get(game_type, game_type.upper())


def provision_step_label(step: str | None) -> str | None:
    if not step:
        return None
    return PROVISION_STEP_LABELS.get(step, step.replace("_", " "))
