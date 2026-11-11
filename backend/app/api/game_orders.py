import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models.game_server import (
    GameOrder,
    GameOrderStatus,
    GameServer,
    GameType,
    PAYMENT_RECONCILE_STATUSES,
)
from app.models.user import User
from app.schemas.game_server import GameOrderCreate, GameOrderResponse
from app.services.abacatepay import (
    ORDER_KIND_GAME,
    AbacatePayService,
    apply_checkout_result,
    has_live_pix,
)
from app.services.game_plan_presets import get_preset
from app.services.game_provisioner import GameProvisioner
from app.services import host_notify

router = APIRouter()
logger = logging.getLogger(__name__)


def _mark_order_failed(db: Session, order_id: int, message: str) -> None:
    db.rollback()
    order = db.get(GameOrder, order_id)
    if not order:
        return
    if order.status in (GameOrderStatus.PROVISIONING, GameOrderStatus.PAID):
        order.status = GameOrderStatus.FAILED
        order.error_message = message[:2000]
        order.provision_step = "failed"
        db.commit()
        host_notify.on_provision_failed(
            db,
            kind="servidor de jogo",
            summary=order.server_name or f"pedido #{order.id}",
            customer_user_id=order.user_id,
            client_url="/dashboard/games",
        )


def _is_mariadb_record_changed(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    return bool(args) and args[0] == 1020


def _try_claim_provisioning(db: Session, order_id: int) -> GameOrder | None:
    try:
        order = (
            db.query(GameOrder)
            .filter(GameOrder.id == order_id, GameOrder.status == GameOrderStatus.PAID)
            .with_for_update()
            .first()
        )
        if not order:
            return None
        order.status = GameOrderStatus.PROVISIONING
        db.commit()
        db.refresh(order)
        return order
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            return None
        raise


def _provision_async(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = _try_claim_provisioning(db, order_id)
        if not order:
            return
        if db.query(GameServer).filter(GameServer.order_id == order.id).first():
            return
        try:
            GameProvisioner().provision_order(db, order)
        except Exception as exc:
            _mark_order_failed(db, order_id, str(exc))
            logger.exception("Provisionamento de jogo falhou para pedido %s", order_id)
    finally:
        db.close()


def mark_game_paid_and_enqueue(
    db: Session,
    order_id: int,
    background_tasks: BackgroundTasks,
) -> bool:
    try:
        order = (
            db.query(GameOrder)
            .filter(
                GameOrder.id == order_id,
                GameOrder.status.in_(PAYMENT_RECONCILE_STATUSES),
            )
            .with_for_update()
            .first()
        )
        if not order:
            return False
        order.status = GameOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        db.commit()
        background_tasks.add_task(_provision_async, order.id)
        host_notify.on_payment_confirmed(
            db,
            kind="servidor de jogo",
            summary=order.server_name or f"pedido #{order.id}",
            total_cents=order.total_cents or 0,
            customer_user_id=order.user_id,
            client_url="/dashboard/games",
            admin_url="/admin?tab=accounts",
        )
        return True
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            return False
        raise


def _attach_checkout(
    db: Session,
    order: GameOrder,
    user: User,
    description: str,
    background_tasks: BackgroundTasks | None,
    *,
    commit: bool = True,
    force_new: bool = False,
) -> None:
    pay = AbacatePayService()
    if (
        pay.payments_required
        and not force_new
        and has_live_pix(order)
        and order.status == GameOrderStatus.PENDING_PAYMENT
    ):
        return

    if order.total_cents <= 0:
        order.status = GameOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        if commit:
            db.commit()
        if background_tasks is not None:
            background_tasks.add_task(_provision_async, order.id)
        if commit:
            host_notify.on_payment_confirmed(
                db,
                kind="servidor de jogo",
                summary=order.server_name or f"pedido #{order.id}",
                total_cents=order.total_cents or 0,
                customer_user_id=order.user_id,
                client_url="/dashboard/games",
                admin_url="/admin?tab=accounts",
            )
        return

    checkout = pay.create_game_checkout(
        order_id=order.id,
        amount_cents=order.total_cents,
        customer_phone=user.phone,
        description=description,
    )
    apply_checkout_result(order, checkout)

    if pay.payments_required:
        if commit:
            db.commit()
    elif pay.payment_bypass_enabled:
        order.status = GameOrderStatus.PAID
        order.provision_progress = 5
        order.provision_step = "payment_confirmed"
        if commit:
            db.commit()
        if background_tasks is not None:
            background_tasks.add_task(_provision_async, order.id)
        if commit:
            host_notify.on_payment_confirmed(
                db,
                kind="servidor de jogo",
                summary=order.server_name or f"pedido #{order.id}",
                total_cents=order.total_cents or 0,
                customer_user_id=order.user_id,
                client_url="/dashboard/games",
                admin_url="/admin?tab=accounts",
            )
    elif commit:
        db.commit()


@router.post("", response_model=GameOrderResponse, status_code=201)
def create_game_order(
    payload: GameOrderCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    game_type = GameType(payload.game_type)
    preset = get_preset(db, payload.preset_id, game_type)
    if not preset:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    order = GameOrder(
        user_id=user.id,
        game_type=game_type,
        preset_id=preset.id,
        slots=preset.slots,
        ram_mb=preset.ram_mb,
        server_name=payload.server_name.strip(),
        total_cents=preset.price_cents,
        status=GameOrderStatus.PENDING_PAYMENT,
        provision_progress=0,
        provision_step="payment_pending",
    )
    description = f"{preset.name} — {payload.server_name.strip()}"
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
            db.refresh(order)
            _attach_checkout(db, order, user, description, background_tasks, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    db.refresh(order)
    if order.status == GameOrderStatus.PENDING_PAYMENT:
        host_notify.on_new_pending_order(
            db,
            kind="servidor de jogo",
            summary=order.server_name or f"pedido #{order.id}",
            total_cents=order.total_cents or 0,
            customer_user_id=order.user_id,
        )
    elif order.status == GameOrderStatus.PAID:
        host_notify.on_payment_confirmed(
            db,
            kind="servidor de jogo",
            summary=order.server_name or f"pedido #{order.id}",
            total_cents=order.total_cents or 0,
            customer_user_id=order.user_id,
            client_url="/dashboard/games",
            admin_url="/admin?tab=accounts",
        )
    return GameOrderResponse.from_order(order)


@router.get("", response_model=list[GameOrderResponse])
def list_game_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = (
        db.query(GameOrder)
        .filter(GameOrder.user_id == user.id)
        .order_by(GameOrder.created_at.desc())
        .all()
    )
    return [GameOrderResponse.from_order(o) for o in orders]


@router.delete("/{order_id}", status_code=204)
def delete_pending_game_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(GameOrder)
            .filter(
                GameOrder.id == order_id,
                GameOrder.user_id == user.id,
                GameOrder.status == GameOrderStatus.PENDING_PAYMENT,
            )
            .with_for_update()
            .first()
        )
    except OperationalError as exc:
        db.rollback()
        if _is_mariadb_record_changed(exc):
            raise HTTPException(status_code=409, detail="Pedido em atualização, tente de novo") from exc
        raise
    if not order:
        existing = db.get(GameOrder, order_id)
        if not existing or existing.user_id != user.id:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        raise HTTPException(
            status_code=400,
            detail="Somente pedidos aguardando pagamento podem ser cancelados",
        )
    order.status = GameOrderStatus.CANCELLED
    order.provision_step = "cancelled_by_user"
    db.commit()


@router.get("/{order_id}", response_model=GameOrderResponse)
def get_game_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(GameOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return GameOrderResponse.from_order(order)


def _game_checkout_description(db: Session, order: GameOrder) -> str:
    preset = get_preset(db, order.preset_id) if order.preset_id else None
    return f"{preset.name if preset else order.game_type.value} — {order.server_name}"


@router.post("/{order_id}/retry-checkout", response_model=GameOrderResponse)
def retry_game_checkout(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(GameOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status != GameOrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Pedido não está aguardando pagamento")

    pay = AbacatePayService()
    if not pay.payments_required:
        raise HTTPException(status_code=400, detail="Pagamento não está habilitado")

    try:
        _attach_checkout(
            db,
            order,
            user,
            _game_checkout_description(db, order),
            background_tasks,
            force_new=not has_live_pix(order),
        )
    except HTTPException:
        db.rollback()
        raise
    db.refresh(order)
    return GameOrderResponse.from_order(order)


@router.post("/{order_id}/sync-payment", response_model=GameOrderResponse)
def sync_game_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(GameOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status not in PAYMENT_RECONCILE_STATUSES:
        return GameOrderResponse.from_order(order)

    pay = AbacatePayService()
    if pay.payments_required:
        if order.status == GameOrderStatus.PENDING_PAYMENT and not has_live_pix(order):
            try:
                _attach_checkout(
                    db,
                    order,
                    user,
                    _game_checkout_description(db, order),
                    background_tasks,
                    force_new=True,
                )
            except HTTPException:
                db.rollback()
                raise
            db.refresh(order)
        if order.payment_external_id and pay.order_is_paid_at_provider(order, ORDER_KIND_GAME):
            mark_game_paid_and_enqueue(db, order.id, background_tasks)
    db.refresh(order)
    return GameOrderResponse.from_order(order)


@router.post("/{order_id}/confirm-payment", response_model=GameOrderResponse)
def confirm_game_payment_test(
    order_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not AbacatePayService().payment_bypass_enabled:
        raise HTTPException(status_code=403, detail="Pagamento real ativo")
    order = db.get(GameOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status not in (GameOrderStatus.PENDING_PAYMENT, GameOrderStatus.PAID):
        raise HTTPException(status_code=400, detail=f"Pedido em status inválido: {order.status}")
    order.status = GameOrderStatus.PAID
    order.provision_progress = 5
    order.provision_step = "payment_confirmed"
    db.commit()
    background_tasks.add_task(_provision_async, order.id)
    db.refresh(order)
    return GameOrderResponse.from_order(order)
