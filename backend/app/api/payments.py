"""Endpoints de pagamento — Abacate Pay."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.game_orders import mark_game_paid_and_enqueue
from app.api.web_orders import mark_web_paid_and_enqueue
from app.api.orders import _mark_paid_and_enqueue
from app.config import get_settings
from app.database import get_db
from app.models.cloud_storage_order import CloudStorageOrder
from app.models.game_server import GameOrder
from app.models.web_site import WebOrder
from app.models.vps import VpsOrder
from app.services.abacatepay import (
    ORDER_KIND_CLOUD,
    ORDER_KIND_GAME,
    ORDER_KIND_VPS,
    ORDER_KIND_WEB,
    AbacatePayService,
)
from app.services.cloud_return import browser_files_url
from app.services.cloud_storage import mark_paid as mark_cloud_storage_paid

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _find_order_by_payment_external_id(db: Session, charge_id: str):
    game_row = db.query(GameOrder).filter(GameOrder.payment_external_id == charge_id).first()
    if game_row:
        return ORDER_KIND_GAME, game_row
    cloud_row = (
        db.query(CloudStorageOrder)
        .filter(CloudStorageOrder.payment_external_id == charge_id)
        .first()
    )
    if cloud_row:
        return ORDER_KIND_CLOUD, cloud_row
    web_row = db.query(WebOrder).filter(WebOrder.payment_external_id == charge_id).first()
    if web_row:
        return ORDER_KIND_WEB, web_row
    vps_row = db.query(VpsOrder).filter(VpsOrder.payment_external_id == charge_id).first()
    if vps_row:
        return ORDER_KIND_VPS, vps_row
    return None, None


@router.get("/config")
def payment_config():
    from app.services.cloud_files import chunk_size_bytes, max_upload_bytes

    pay = AbacatePayService()
    upload_limit = max_upload_bytes()
    return {
        "payments_required": pay.payments_required,
        "provider": "abacatepay",
        "skip_payment_for_testing": settings.skip_payment_for_testing,
        "cloud_max_upload_bytes": upload_limit,
        "cloud_max_upload_gb": round(upload_limit / (1024**3), 2),
        "cloud_chunk_size_bytes": chunk_size_bytes(),
    }


@router.get("/cloud-storage/complete")
def cloud_storage_payment_complete(
    order: int | None = Query(default=None),
):
    """Retorno de browser: não consulta pedido, não credita e não revela metadados.

    O crédito ocorre no webhook autenticado ou em POST /api/files/storage/... com o dono logado.
    """
    del order
    return RedirectResponse(url=browser_files_url(), status_code=302)


@router.post("/webhook/abacatepay")
async def abacatepay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    webhook_secret: str | None = Query(default=None, alias="webhookSecret"),
    db: Session = Depends(get_db),
):
    body = await request.body()
    pay = AbacatePayService()
    pay.require_authenticated_webhook(
        body,
        webhook_secret,
        request.headers.get("X-Webhook-Signature", ""),
    )

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON inválido") from exc

    if not AbacatePayService.is_payment_confirmed_event(payload):
        return {"received": True, "processed": False}

    charge_id = AbacatePayService.extract_charge_id(payload)
    if not charge_id:
        logger.warning("Webhook AbacatePay sem charge_id vinculado")
        return {"received": True, "processed": False}

    kind, order = _find_order_by_payment_external_id(db, charge_id)
    if order is None or kind is None:
        logger.warning("Webhook AbacatePay sem pedido para charge_id=%s", charge_id)
        return {"received": True, "processed": False}

    try:
        pay.verify_paid_charge_for_order(order, kind, webhook_payload=payload)
    except HTTPException as exc:
        if exc.status_code >= 500:
            raise
        logger.warning(
            "Webhook AbacatePay rejeitou charge_id=%s order_id=%s: %s",
            charge_id,
            order.id,
            exc.detail,
        )
        return {"received": True, "processed": False, "charge_id": charge_id}

    if kind == ORDER_KIND_GAME:
        if mark_game_paid_and_enqueue(db, order.id, background_tasks):
            logger.info("Pagamento game server confirmado order_id=%s", order.id)
            return {"received": True, "processed": True, "game_order_id": order.id}
        return {"received": True, "processed": False, "game_order_id": order.id}

    if kind == ORDER_KIND_CLOUD:
        if mark_cloud_storage_paid(db, order.id):
            logger.info("Pagamento CyberCloud confirmado order_id=%s", order.id)
            return {"received": True, "processed": True, "cloud_storage_order_id": order.id}
        return {"received": True, "processed": False, "cloud_storage_order_id": order.id}

    if kind == ORDER_KIND_WEB:
        if mark_web_paid_and_enqueue(db, order.id, background_tasks):
            logger.info("Pagamento site confirmado order_id=%s", order.id)
            return {"received": True, "processed": True, "web_order_id": order.id}
        return {"received": True, "processed": False, "web_order_id": order.id}

    if _mark_paid_and_enqueue(db, order.id, background_tasks):
        logger.info("Pagamento confirmado para pedido %s", order.id)
        return {"received": True, "processed": True, "order_id": order.id}

    return {"received": True, "processed": False, "order_id": order.id}
