"""Validação, reserva e redenção atômica de cupons de desconto."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.models.coupon import CouponRedemption, DiscountCoupon

logger = logging.getLogger(__name__)


def normalize_coupon_code(code: str) -> str:
    return code.strip().upper()


def _for_update(query: Query, db: Session) -> Query:
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        return query.with_for_update()
    return query


def _coupon_by_code(db: Session, code: str, *, lock: bool) -> DiscountCoupon | None:
    normalized = normalize_coupon_code(code)
    if not normalized:
        return None
    query = db.query(DiscountCoupon).filter(DiscountCoupon.code == normalized)
    if lock:
        query = _for_update(query, db)
    return query.first()


def _coupon_by_id(db: Session, coupon_id: int, *, lock: bool) -> DiscountCoupon | None:
    query = db.query(DiscountCoupon).filter(DiscountCoupon.id == coupon_id)
    if lock:
        query = _for_update(query, db)
    return query.first()


def get_coupon_by_code(db: Session, code: str) -> DiscountCoupon | None:
    return _coupon_by_code(db, code, lock=False)


def validate_coupon(coupon: DiscountCoupon, *, now: datetime | None = None) -> None:
    now = now or datetime.utcnow()
    if not coupon.is_active:
        raise HTTPException(status_code=400, detail="Cupom inativo")
    if coupon.valid_from and now < coupon.valid_from:
        raise HTTPException(status_code=400, detail="Cupom ainda não está válido")
    if coupon.valid_until and now > coupon.valid_until:
        raise HTTPException(status_code=400, detail="Cupom expirado")
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="Cupom esgotado")
    if not coupon.discount_percent and not coupon.discount_cents:
        raise HTTPException(status_code=400, detail="Cupom sem desconto configurado")
    if coupon.discount_percent and coupon.discount_cents:
        raise HTTPException(status_code=400, detail="Cupom com configuração inválida")


def calculate_discount(coupon: DiscountCoupon, subtotal_cents: int) -> int:
    if subtotal_cents <= 0:
        return 0
    if coupon.discount_percent:
        return min(subtotal_cents, int(subtotal_cents * coupon.discount_percent / 100))
    if coupon.discount_cents:
        return min(subtotal_cents, coupon.discount_cents)
    return 0


def apply_coupon_to_subtotal(
    db: Session,
    code: str | None,
    subtotal_cents: int,
) -> tuple[int, int, DiscountCoupon | None]:
    """Prévia de cotação — não reserva vaga. Retorna (discount_cents, total_cents, coupon)."""
    if not code or not code.strip():
        return 0, subtotal_cents, None

    coupon = get_coupon_by_code(db, code)
    if not coupon:
        raise HTTPException(status_code=400, detail="Cupom inválido")

    validate_coupon(coupon)
    discount = calculate_discount(coupon, subtotal_cents)
    if discount <= 0:
        raise HTTPException(status_code=400, detail="Cupom não aplicável a este valor")
    return discount, max(0, subtotal_cents - discount), coupon


def reserve_coupon_for_order(
    db: Session,
    code: str | None,
    subtotal_cents: int,
) -> tuple[int, int, DiscountCoupon | None]:
    """Reserva uma vaga sob lock (used_count += 1). Não faz commit."""
    if not code or not code.strip():
        return 0, subtotal_cents, None

    coupon = _coupon_by_code(db, code, lock=True)
    if not coupon:
        raise HTTPException(status_code=400, detail="Cupom inválido")

    validate_coupon(coupon)
    discount = calculate_discount(coupon, subtotal_cents)
    if discount <= 0:
        raise HTTPException(status_code=400, detail="Cupom não aplicável a este valor")
    coupon.used_count += 1
    db.flush()
    return discount, max(0, subtotal_cents - discount), coupon


def _redemption_count(db: Session, coupon_id: int) -> int:
    return (
        db.query(CouponRedemption)
        .filter(CouponRedemption.coupon_id == coupon_id)
        .count()
    )


def redeem_coupon_for_order(db: Session, order_id: int, coupon_id: int) -> None:
    _redeem_coupon(db, coupon_id, order_id=order_id)


def redeem_coupon_for_web_order(db: Session, web_order_id: int, coupon_id: int) -> None:
    _redeem_coupon(db, coupon_id, web_order_id=web_order_id)


def _redemption_for(
    db: Session,
    *,
    order_id: int | None = None,
    web_order_id: int | None = None,
) -> CouponRedemption | None:
    if order_id is not None:
        return (
            db.query(CouponRedemption)
            .filter(CouponRedemption.order_id == order_id)
            .first()
        )
    if web_order_id is not None:
        return (
            db.query(CouponRedemption)
            .filter(CouponRedemption.web_order_id == web_order_id)
            .first()
        )
    return None


def _redeem_coupon(
    db: Session,
    coupon_id: int,
    *,
    order_id: int | None = None,
    web_order_id: int | None = None,
) -> None:
    existing = _redemption_for(db, order_id=order_id, web_order_id=web_order_id)
    if existing:
        return

    coupon = _coupon_by_id(db, coupon_id, lock=True)
    if not coupon:
        return

    existing = _for_update(
        db.query(CouponRedemption).filter(
            CouponRedemption.order_id == order_id
            if order_id is not None
            else CouponRedemption.web_order_id == web_order_id
        ),
        db,
    ).first()
    if existing:
        return

    already_reserved = coupon.used_count > _redemption_count(db, coupon_id)
    if not already_reserved:
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            logger.warning(
                "Cupom %s esgotado na redenção do pedido %s; teto preservado",
                coupon_id,
                order_id or web_order_id,
            )
        else:
            coupon.used_count += 1

    db.add(
        CouponRedemption(
            coupon_id=coupon_id,
            order_id=order_id,
            web_order_id=web_order_id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def release_coupon_reservation(db: Session, order_id: int, coupon_id: int | None) -> None:
    """Devolve a vaga de um pedido VPS pendente. Não faz commit."""
    _release_coupon_reservation(db, coupon_id, order_id=order_id)


def release_web_coupon_reservation(db: Session, web_order_id: int, coupon_id: int | None) -> None:
    """Devolve a vaga de um pedido de site pendente. Não faz commit."""
    _release_coupon_reservation(db, coupon_id, web_order_id=web_order_id)


def _release_coupon_reservation(
    db: Session,
    coupon_id: int | None,
    *,
    order_id: int | None = None,
    web_order_id: int | None = None,
) -> None:
    if not coupon_id:
        return
    existing = _redemption_for(db, order_id=order_id, web_order_id=web_order_id)
    if existing:
        return

    coupon = _coupon_by_id(db, coupon_id, lock=True)
    if not coupon:
        return
    if coupon.used_count > 0:
        coupon.used_count -= 1
    db.flush()
