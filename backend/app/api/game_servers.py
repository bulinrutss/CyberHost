from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models.game_server import GameOrder, GameOrderStatus, GameServer, GameServerStatus, GameType
from app.models.user import User
from app.schemas.game_server import (
    GameFileContent,
    GameFileEntry,
    GameFileWrite,
    GameLogsResponse,
    GamePresetResponse,
    GameQuoteRequest,
    GameQuoteResponse,
    GameServerDetail,
    GameServerResponse,
    GameTypeInfo,
)
from app.services.game_files import list_directory, read_file, upload_file, write_file
from app.services.game_meta import CONFIG_FILES, DEFAULT_PORTS, GAME_TYPE_DESCRIPTIONS, game_type_label
from app.services.game_plan_presets import get_preset, list_presets
from app.services.game_process import restart_server, start_server, stop_server, sync_server_status, tail_logs

router = APIRouter()


def _resolve_server(db: Session, server_id: int, user: User) -> GameServer:
    server = (
        db.query(GameServer)
        .options(joinedload(GameServer.host), joinedload(GameServer.order))
        .filter(GameServer.id == server_id, GameServer.user_id == user.id)
        .first()
    )
    if not server or server.status == GameServerStatus.DELETED:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    return server


def _server_response(server: GameServer) -> GameServerResponse:
    order = server.order
    is_provisioning = bool(
        order
        and order.status in (GameOrderStatus.PAID, GameOrderStatus.PROVISIONING)
    )
    public_ip = server.host.public_ip if server.host else "127.0.0.1"
    game = server.game_type.value if isinstance(server.game_type, GameType) else str(server.game_type)
    return GameServerResponse(
        id=server.id,
        game_type=game,
        game_label=game_type_label(game),
        server_name=server.server_name,
        slots=server.slots,
        ram_mb=server.ram_mb,
        port=server.port,
        query_port=server.query_port,
        public_ip=public_ip,
        address=f"{public_ip}:{server.port}",
        status=server.status.value if isinstance(server.status, GameServerStatus) else server.status,
        is_provisioning=is_provisioning,
        config_file=CONFIG_FILES.get(game, "server.cfg"),
        error_message=server.error_message,
        billing={
            "paid_until": server.paid_until,
            "billing_day": server.billing_day,
            "monthly_cents": order.total_cents if order else 0,
            "suspended_for_billing": server.suspended_for_billing,
        }
        if server.paid_until
        else None,
        created_at=server.created_at,
    )


@router.get("/types", response_model=list[GameTypeInfo])
def list_game_types():
    return [
        GameTypeInfo(
            slug=gt.value,
            label=game_type_label(gt.value),
            description=GAME_TYPE_DESCRIPTIONS[gt.value],
            default_port=DEFAULT_PORTS[gt.value],
        )
        for gt in GameType
    ]


@router.get("/presets", response_model=list[GamePresetResponse])
def list_game_presets(
    game_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    gt = GameType(game_type) if game_type else None
    return list_presets(db, gt)


@router.post("/quote", response_model=GameQuoteResponse)
def quote_game_server(payload: GameQuoteRequest, db: Session = Depends(get_db)):
    game_type = GameType(payload.game_type)
    preset = get_preset(db, payload.preset_id, game_type)
    if not preset:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    return GameQuoteResponse(
        game_type=preset.game_type.value,
        preset_id=preset.id,
        slots=preset.slots,
        ram_mb=preset.ram_mb,
        total_cents=preset.price_cents,
        monthly_cents=preset.price_cents,
    )


@router.get("/instances", response_model=list[GameServerResponse])
def list_instances(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    servers = (
        db.query(GameServer)
        .options(joinedload(GameServer.host), joinedload(GameServer.order))
        .filter(GameServer.user_id == user.id, GameServer.status != GameServerStatus.DELETED)
        .order_by(GameServer.created_at.desc())
        .all()
    )
    return [_server_response(s) for s in servers]


@router.get("/instances/{server_id}", response_model=GameServerDetail)
def get_instance(
    server_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    base = _server_response(server)
    order = server.order
    return GameServerDetail(
        **base.model_dump(),
        provision_progress=order.provision_progress if order else None,
        provision_label=None,
    )


@router.post("/instances/{server_id}/start")
def start_instance(
    server_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    if server.suspended_for_billing:
        raise HTTPException(status_code=403, detail="Servidor suspenso por inadimplência")
    if server.status == GameServerStatus.CREATING:
        raise HTTPException(status_code=400, detail="Servidor ainda está sendo criado")
    try:
        pid = start_server(server)
        server.process_pid = pid
        server.status = GameServerStatus.RUNNING
        server.error_message = None
        db.commit()
    except Exception as exc:
        server.status = GameServerStatus.ERROR
        server.error_message = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running", "pid": pid}


@router.post("/instances/{server_id}/stop")
def stop_instance(
    server_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    stop_server(server)
    server.process_pid = None
    server.status = GameServerStatus.STOPPED
    db.commit()
    return {"status": "stopped"}


@router.post("/instances/{server_id}/restart")
def restart_instance(
    server_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    if server.suspended_for_billing:
        raise HTTPException(status_code=403, detail="Servidor suspenso por inadimplência")
    try:
        pid = restart_server(server)
        server.process_pid = pid
        server.status = GameServerStatus.RUNNING
        server.error_message = None
        db.commit()
    except Exception as exc:
        server.status = GameServerStatus.ERROR
        server.error_message = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running", "pid": pid}


@router.get("/instances/{server_id}/status")
def instance_status(
    server_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    live = sync_server_status(server)
    if live != server.status:
        server.status = live
        if live == GameServerStatus.STOPPED:
            server.process_pid = None
        db.commit()
    return {"status": server.status.value, "pid": server.process_pid}


@router.get("/instances/{server_id}/logs", response_model=GameLogsResponse)
def instance_logs(
    server_id: int,
    tail: int = Query(default=100, ge=10, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    return GameLogsResponse(lines=tail_logs(server.data_path, tail), tail=tail)


@router.get("/instances/{server_id}/files", response_model=list[GameFileEntry])
def list_files(
    server_id: int,
    path: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    return list_directory(server, path)


@router.get("/instances/{server_id}/files/content", response_model=GameFileContent)
def get_file_content(
    server_id: int,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    return GameFileContent(path=path, content=read_file(server, path))


@router.put("/instances/{server_id}/files/content")
def save_file_content(
    server_id: int,
    payload: GameFileWrite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    write_file(server, payload.path, payload.content)
    return {"ok": True}


@router.post("/instances/{server_id}/files/upload")
async def upload_server_file(
    server_id: int,
    path: str = Query(default=""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _resolve_server(db, server_id, user)
    return upload_file(server, path, file)
