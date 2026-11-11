"""Seed e consulta de planos predefinidos para servidores de jogo."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.game_server import GamePlanPreset, GameType

GAME_PRESETS = [
    # SA-MP
    {
        "game_type": GameType.SAMP,
        "slug": "samp_50",
        "name": "SAMP 50 slots",
        "slots": 50,
        "ram_mb": 512,
        "price_cents": 1990,
        "sort_order": 1,
    },
    {
        "game_type": GameType.SAMP,
        "slug": "samp_100",
        "name": "SAMP 100 slots",
        "slots": 100,
        "ram_mb": 1024,
        "price_cents": 2990,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "game_type": GameType.SAMP,
        "slug": "samp_200",
        "name": "SAMP 200 slots",
        "slots": 200,
        "ram_mb": 2048,
        "price_cents": 4990,
        "sort_order": 3,
    },
    # MTA
    {
        "game_type": GameType.MTA,
        "slug": "mta_50",
        "name": "MTA 50 slots",
        "slots": 50,
        "ram_mb": 1024,
        "price_cents": 2490,
        "sort_order": 1,
    },
    {
        "game_type": GameType.MTA,
        "slug": "mta_100",
        "name": "MTA 100 slots",
        "slots": 100,
        "ram_mb": 2048,
        "price_cents": 3990,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "game_type": GameType.MTA,
        "slug": "mta_200",
        "name": "MTA 200 slots",
        "slots": 200,
        "ram_mb": 4096,
        "price_cents": 5990,
        "sort_order": 3,
    },
    # Minecraft
    {
        "game_type": GameType.MINECRAFT,
        "slug": "mc_10",
        "name": "Minecraft 10 jogadores",
        "slots": 10,
        "ram_mb": 2048,
        "price_cents": 2990,
        "sort_order": 1,
    },
    {
        "game_type": GameType.MINECRAFT,
        "slug": "mc_20",
        "name": "Minecraft 20 jogadores",
        "slots": 20,
        "ram_mb": 4096,
        "price_cents": 4990,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "game_type": GameType.MINECRAFT,
        "slug": "mc_50",
        "name": "Minecraft 50 jogadores",
        "slots": 50,
        "ram_mb": 8192,
        "price_cents": 8990,
        "sort_order": 3,
    },
    # FiveM
    {
        "game_type": GameType.FIVEM,
        "slug": "fivem_32",
        "name": "FiveM 32 slots",
        "slots": 32,
        "ram_mb": 4096,
        "price_cents": 4990,
        "sort_order": 1,
    },
    {
        "game_type": GameType.FIVEM,
        "slug": "fivem_64",
        "name": "FiveM 64 slots",
        "slots": 64,
        "ram_mb": 6144,
        "price_cents": 7990,
        "is_popular": True,
        "sort_order": 2,
    },
    {
        "game_type": GameType.FIVEM,
        "slug": "fivem_128",
        "name": "FiveM 128 slots",
        "slots": 128,
        "ram_mb": 8192,
        "price_cents": 12990,
        "sort_order": 3,
    },
]


def seed_game_plan_presets(db: Session) -> None:
    for preset_def in GAME_PRESETS:
        existing = (
            db.query(GamePlanPreset)
            .filter(
                GamePlanPreset.game_type == preset_def["game_type"],
                GamePlanPreset.slug == preset_def["slug"],
            )
            .first()
        )
        if existing:
            existing.name = preset_def["name"]
            existing.slots = preset_def["slots"]
            existing.ram_mb = preset_def["ram_mb"]
            existing.price_cents = preset_def["price_cents"]
            existing.is_popular = preset_def.get("is_popular", False)
            existing.sort_order = preset_def.get("sort_order", 0)
            existing.is_active = True
        else:
            db.add(GamePlanPreset(**preset_def))
    db.commit()


def list_presets(db: Session, game_type: GameType | None = None) -> list[GamePlanPreset]:
    query = db.query(GamePlanPreset).filter(GamePlanPreset.is_active.is_(True))
    if game_type:
        query = query.filter(GamePlanPreset.game_type == game_type)
    return query.order_by(GamePlanPreset.sort_order, GamePlanPreset.id).all()


def get_preset(db: Session, preset_id: int, game_type: GameType | None = None) -> GamePlanPreset | None:
    query = db.query(GamePlanPreset).filter(
        GamePlanPreset.id == preset_id,
        GamePlanPreset.is_active.is_(True),
    )
    if game_type:
        query = query.filter(GamePlanPreset.game_type == game_type)
    return query.first()
