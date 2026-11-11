"""Ferramenta admin: colar Pix DevMode e creditar o pedido correspondente."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.models.cloud_storage_order import (
    PAYMENT_RECONCILE_STATUSES as CLOUD_RECONCILE,
    CloudStorageOrder,
)
from app.models.game_server import (
    PAYMENT_RECONCILE_STATUSES as GAME_RECONCILE,
    GameOrder,
)
from app.models.web_site import (
    PAYMENT_RECONCILE_STATUSES as WEB_RECONCILE,
    WebOrder,
)
from app.models.vps import PAYMENT_RECONCILE_STATUSES as VPS_RECONCILE, VpsOrder
from app.services.abacatepay import (
    ORDER_KIND_CLOUD,
    ORDER_KIND_GAME,
    ORDER_KIND_VPS,
    ORDER_KIND_WEB,
    PAID_STATUSES,
    AbacatePayService,
)


def _merge_charge(base: dict, extra: dict | None) -> dict:
    extra = extra if isinstance(extra, dict) else {}
    merged = {**base, **{key: value for key, value in extra.items() if value is not None}}
    base_meta = base.get("metadata") if isinstance(base.get("metadata"), dict) else {}
    extra_meta = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
    if base_meta or extra_meta:
        merged["metadata"] = {**base_meta, **extra_meta}
    return merged


def _needs_provider_details(charge: dict) -> bool:
    meta = charge.get("metadata")
    has_meta = isinstance(meta, dict) and bool(meta)
    return charge.get("amount") is None or not has_meta


logger = logging.getLogger(__name__)

CHARGE_RE = re.compile(r"pix[_-]?char[_-]([A-Za-z0-9]{6,40})", re.IGNORECASE)
_EMV_SUFFIX = re.compile(r"(?:52|53|54|58|59|60|62|63)\d{2}[A-Za-z0-9]*$")
MAX_CHARGES = 20
MAX_TEXT = 20000
_MIN_BR_CODE = 40


def _normalize_blob(blob: str) -> str:
    text = (blob or "").replace("\ufeff", "").replace("\u00a0", " ")
    text = re.sub(r"[\u200b-\u200d\u2060]", "", text)
    if re.search(r"%[0-9A-Fa-f]{2}", text):
        try:
            text = unquote(text)
        except Exception:
            pass
    return text


def _compact_br(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def extract_charge_ids(blob: str, *, limit: int = MAX_CHARGES) -> list[str]:
    text = _normalize_blob(blob)
    collapsed = re.sub(r"(pix[_-]?char[_-])\s+", r"\1", text, flags=re.IGNORECASE)
    seen: list[str] = []
    for source in (text, collapsed):
        for match in CHARGE_RE.finditer(source):
            body = _EMV_SUFFIX.sub("", match.group(1))
            if len(body) < 6:
                continue
            cid = f"pix_char_{body}"
            if cid in seen:
                continue
            seen.append(cid)
            if len(seen) >= limit:
                return seen
    return seen


def _br_codes_match(pasted: str, stored: str | None) -> bool:
    left = _compact_br(pasted)
    right = _compact_br(stored or "")
    if len(left) < _MIN_BR_CODE or len(right) < _MIN_BR_CODE:
        return False
    prefix = 80
    return left == right or left.startswith(right[:prefix]) or right.startswith(left[:prefix])


def find_charge_ids_by_br_code(db: Session, blob: str, *, limit: int = MAX_CHARGES) -> list[str]:
    pasted = _normalize_blob(blob)
    if len(_compact_br(pasted)) < _MIN_BR_CODE:
        return []
    seen: list[str] = []
    queries = (
        db.query(GameOrder).filter(GameOrder.pix_br_code.isnot(None)),
        db.query(CloudStorageOrder).filter(CloudStorageOrder.pix_br_code.isnot(None)),
        db.query(VpsOrder).filter(VpsOrder.pix_br_code.isnot(None)),
        db.query(WebOrder).filter(WebOrder.pix_br_code.isnot(None)),
    )
    for query in queries:
        for order in query.all():
            if not _br_codes_match(pasted, order.pix_br_code):
                continue
            cid = str(order.payment_external_id or "").strip()
            if not cid.startswith("pix_char_") or cid in seen:
                continue
            seen.append(cid)
            if len(seen) >= limit:
                return seen
    return seen


@dataclass
class PixDevResult:
    charge_id: str
    ok: bool
    action: str
    detail: str
    kind: str | None = None
    order_id: int | None = None
    order_status: str | None = None
    simulated: bool = False


def find_order(db: Session, charge_id: str):
    game = db.query(GameOrder).filter(GameOrder.payment_external_id == charge_id).first()
    if game:
        return ORDER_KIND_GAME, game
    cloud = (
        db.query(CloudStorageOrder)
        .filter(CloudStorageOrder.payment_external_id == charge_id)
        .first()
    )
    if cloud:
        return ORDER_KIND_CLOUD, cloud
    vps = db.query(VpsOrder).filter(VpsOrder.payment_external_id == charge_id).first()
    if vps:
        return ORDER_KIND_VPS, vps
    web = db.query(WebOrder).filter(WebOrder.payment_external_id == charge_id).first()
    if web:
        return ORDER_KIND_WEB, web
    return None, None


def _status_value(order: object) -> str:
    status = getattr(order, "status", None)
    return str(getattr(status, "value", status) or "")


def _already_credited(kind: str, order: object) -> bool:
    status = getattr(order, "status", None)
    if kind == ORDER_KIND_VPS:
        return status not in VPS_RECONCILE
    if kind == ORDER_KIND_GAME:
        return status not in GAME_RECONCILE
    if kind == ORDER_KIND_WEB:
        return status not in WEB_RECONCILE
    return status not in CLOUD_RECONCILE


def _http_detail(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    return "Falha ao processar cobrança"


def _credit(db: Session, kind: str, order_id: int, background_tasks: BackgroundTasks) -> bool:
    if kind == ORDER_KIND_GAME:
        from app.api.game_orders import mark_game_paid_and_enqueue

        return mark_game_paid_and_enqueue(db, order_id, background_tasks)
    if kind == ORDER_KIND_CLOUD:
        from app.services.cloud_storage import mark_paid

        return mark_paid(db, order_id)
    if kind == ORDER_KIND_WEB:
        from app.api.web_orders import mark_web_paid_and_enqueue

        return mark_web_paid_and_enqueue(db, order_id, background_tasks)
    from app.api.orders import _mark_paid_and_enqueue

    return _mark_paid_and_enqueue(db, order_id, background_tasks)


def _failed(
    charge_id: str,
    detail: str,
    *,
    kind: str | None = None,
    order: object | None = None,
    simulated: bool = False,
) -> PixDevResult:
    return PixDevResult(
        charge_id=charge_id,
        ok=False,
        action="failed",
        detail=detail,
        kind=kind,
        order_id=getattr(order, "id", None) if order is not None else None,
        order_status=_status_value(order) if order is not None else None,
        simulated=simulated,
    )


def release_charge(
    db: Session,
    charge_id: str,
    background_tasks: BackgroundTasks,
    pay: AbacatePayService | None = None,
) -> PixDevResult:
    pay = pay or AbacatePayService()
    kind, order = find_order(db, charge_id)
    if order is None or kind is None:
        return _failed(charge_id, "Pedido não encontrado")
    if _already_credited(kind, order):
        return PixDevResult(
            charge_id=charge_id,
            ok=True,
            action="already",
            detail="Pedido já liberado",
            kind=kind,
            order_id=order.id,
            order_status=_status_value(order),
        )

    simulated = False
    try:
        charge = pay.fetch_charge(charge_id)
        if pay.is_explicit_live_charge(charge):
            return _failed(
                charge_id,
                "Só cobranças DevMode. Para Pix ao vivo use a sincronização do pedido.",
                kind=kind,
                order=order,
            )
        status_now = (charge.get("status") or "").upper()
        if status_now not in PAID_STATUSES or _needs_provider_details(charge):
            simulated_payload = pay.simulate_sandbox_payment(charge_id)
            simulated = True
            charge = _merge_charge(charge, simulated_payload)
        if pay.is_explicit_live_charge(charge):
            return _failed(
                charge_id,
                "Só cobranças DevMode. Para Pix ao vivo use a sincronização do pedido.",
                kind=kind,
                order=order,
                simulated=simulated,
            )
        if not str(charge.get("id") or "").strip():
            charge["id"] = charge_id
        pay.assert_paid_charge(
            charge,
            expected_id=charge_id,
            expected_amount_cents=int(order.total_cents),
            expected_kind=kind,
            expected_order_id=int(order.id),
            allow_dev_mode=True,
        )
    except HTTPException as exc:
        return _failed(
            charge_id,
            _http_detail(exc),
            kind=kind,
            order=order,
            simulated=simulated,
        )

    credited = _credit(db, kind, order.id, background_tasks)
    db.refresh(order)
    if not credited:
        return _failed(
            charge_id,
            "Não foi possível marcar o pedido como pago",
            kind=kind,
            order=order,
            simulated=simulated,
        )
    logger.info(
        "PixDev creditou charge_id=%s kind=%s order_id=%s simulated=%s",
        charge_id,
        kind,
        order.id,
        simulated,
    )
    return PixDevResult(
        charge_id=charge_id,
        ok=True,
        action="released",
        detail="Liberado como pago",
        kind=kind,
        order_id=order.id,
        order_status=_status_value(order),
        simulated=simulated,
    )


def release_text(
    db: Session,
    text: str,
    background_tasks: BackgroundTasks,
    pay: AbacatePayService | None = None,
) -> list[PixDevResult]:
    blob = (text or "").strip()
    if not blob:
        raise HTTPException(status_code=400, detail="Cole o código Pix, o link ou o id da cobrança")
    if len(blob) > MAX_TEXT:
        raise HTTPException(status_code=400, detail="Texto grande demais")
    ids = extract_charge_ids(blob)
    if not ids:
        ids = find_charge_ids_by_br_code(db, blob)
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="Nenhum pix_char_ nem código Pix de pedido encontrado",
        )
    return [release_charge(db, cid, background_tasks, pay=pay) for cid in ids]
