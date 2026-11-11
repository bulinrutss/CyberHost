"""Provisionamento de servidores de jogo: porta, arquivos e configuração."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings, get_settings as app_get_settings
from app.models.game_server import (
    GameHost,
    GameOrder,
    GameOrderStatus,
    GameServer,
    GameServerStatus,
    GameType,
)
from app.services.billing import initial_paid_until
from app.services.game_meta import CONFIG_FILES, DEFAULT_PORTS, PORT_RANGES

logger = logging.getLogger(__name__)

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "game_templates"


def _templates_dir(game_type: GameType) -> Path:
    return TEMPLATES_ROOT / game_type.value


def _update_order_progress(db: Session, order: GameOrder, *, progress: int, step: str) -> None:
    order.provision_progress = progress
    order.provision_step = step
    db.commit()


def _default_host(db: Session, settings: Settings) -> GameHost:
    host = db.query(GameHost).filter(GameHost.is_active.is_(True)).order_by(GameHost.id).first()
    if host:
        return host
    host = GameHost(
        name="Host principal",
        public_ip=settings.game_host_public_ip,
        data_path=settings.game_servers_data_path,
        port_range_start=settings.game_port_range_start,
        port_range_end=settings.game_port_range_end,
        max_servers=settings.game_host_max_servers,
        is_active=True,
    )
    db.add(host)
    db.flush()
    return host


def _allocate_port(db: Session, host: GameHost, game_type: GameType) -> tuple[int, int | None]:
    start, end = PORT_RANGES.get(game_type.value, (host.port_range_start, host.port_range_end))
    used = {
        row[0]
        for row in db.query(GameServer.port)
        .filter(GameServer.host_id == host.id, GameServer.status != GameServerStatus.DELETED)
        .all()
    }
    for port in range(start, end + 1):
        if port not in used:
            query_port = port + 1 if game_type == GameType.SAMP else None
            if query_port and query_port in used:
                continue
            return port, query_port
    raise ValueError(f"Sem portas disponíveis para {game_type.value} no host {host.name}")


def _server_data_path(host: GameHost, user_id: int, server_id: int) -> str:
    return str(Path(host.data_path) / str(user_id) / str(server_id))


def _deploy_template(game_type: GameType, dest: Path, *, server_name: str, port: int, slots: int) -> None:
    src = _templates_dir(game_type)
    if not src.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)

    if game_type == GameType.SAMP:
        cfg = dest / "server.cfg"
        if cfg.is_file():
            text = cfg.read_text(encoding="utf-8")
            text = text.replace("{{HOSTNAME}}", server_name)
            text = text.replace("{{PORT}}", str(port))
            text = text.replace("{{MAXPLAYERS}}", str(slots))
            cfg.write_text(text, encoding="utf-8")
    elif game_type == GameType.MTA:
        conf = dest / "mods" / "deathmatch" / "mtaserver.conf"
        if conf.is_file():
            text = conf.read_text(encoding="utf-8")
            text = text.replace("{{SERVER_NAME}}", server_name)
            text = text.replace("{{PORT}}", str(port))
            text = text.replace("{{MAX_PLAYERS}}", str(slots))
            conf.write_text(text, encoding="utf-8")
    elif game_type == GameType.MINECRAFT:
        props = dest / "server.properties"
        if props.is_file():
            text = props.read_text(encoding="utf-8")
            text = text.replace("{{MOTD}}", server_name)
            text = text.replace("{{PORT}}", str(port))
            text = text.replace("{{MAX_PLAYERS}}", str(slots))
            props.write_text(text, encoding="utf-8")
    elif game_type == GameType.FIVEM:
        cfg = dest / "server.cfg"
        if cfg.is_file():
            license_key = app_get_settings().game_fivem_default_license_key or "changeme"
            text = cfg.read_text(encoding="utf-8")
            text = text.replace("{{SERVER_NAME}}", server_name)
            text = text.replace("{{PORT}}", str(port))
            text = text.replace("{{MAX_PLAYERS}}", str(slots))
            text = text.replace("{{LICENSE_KEY}}", license_key)
            cfg.write_text(text, encoding="utf-8")


class GameProvisioner:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or app_get_settings()

    def provision_order(self, db: Session, order: GameOrder) -> GameServer:
        existing = db.query(GameServer).filter(GameServer.order_id == order.id).first()
        if existing:
            return existing

        _update_order_progress(db, order, progress=15, step="allocating_port")
        host = _default_host(db, self.settings)
        port, query_port = _allocate_port(db, host, order.game_type)

        server = GameServer(
            user_id=order.user_id,
            order_id=order.id,
            host_id=host.id,
            game_type=order.game_type,
            server_name=order.server_name,
            slots=order.slots,
            ram_mb=order.ram_mb,
            port=port,
            query_port=query_port,
            data_path="",
            status=GameServerStatus.CREATING,
        )
        db.add(server)
        db.flush()

        server.data_path = _server_data_path(host, order.user_id, server.id)
        db.commit()

        _update_order_progress(db, order, progress=40, step="deploying_files")
        dest = Path(server.data_path)
        _deploy_template(
            order.game_type,
            dest,
            server_name=order.server_name,
            port=port,
            slots=order.slots,
        )

        _update_order_progress(db, order, progress=80, step="configuring")
        paid_until, billing_day = initial_paid_until()
        server.status = GameServerStatus.STOPPED
        server.paid_until = paid_until
        server.billing_day = billing_day

        order.status = GameOrderStatus.ACTIVE
        _update_order_progress(db, order, progress=100, step="ready")
        db.refresh(server)
        from app.services import host_notify

        host_notify.on_provision_ready(
            db,
            kind="Servidor de jogo",
            summary=order.server_name or f"pedido #{order.id}",
            customer_user_id=order.user_id,
            client_url="/dashboard/games",
        )
        logger.info(
            "Servidor de jogo provisionado id=%s tipo=%s porta=%s",
            server.id,
            order.game_type.value,
            port,
        )
        return server
