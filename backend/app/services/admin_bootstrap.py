"""Bootstrap da conta administrativa — cria só se ausente; nunca redefine senha."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.database import SessionLocal
from app.models.user import User
from app.utils.phone import validate_phone

logger = logging.getLogger(__name__)


def seed_admin_user(
    db: Session | None = None,
    *,
    admin_phone: str | None = None,
    admin_password: str | None = None,
) -> str:
    """Cria o admin só se o telefone ainda não existir. Nunca redefine senha no startup.

    Retornos: ``created``, ``exists`` ou ``skipped``.
    """
    settings = get_settings()
    phone_raw = settings.admin_phone if admin_phone is None else admin_phone
    password = settings.admin_password if admin_password is None else admin_password

    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        try:
            phone = validate_phone(phone_raw)
        except ValueError:
            logger.warning("ADMIN_PHONE inválido; bootstrap de admin ignorado")
            return "skipped"

        existing = db.query(User).filter(User.phone == phone).first()
        if existing:
            logger.info("Conta administrativa já existe; senha do ambiente não será aplicada")
            return "exists"

        if not password:
            logger.warning(
                "Nenhuma conta com ADMIN_PHONE e ADMIN_PASSWORD vazio; admin não criado"
            )
            return "skipped"

        db.add(
            User(
                phone=phone,
                name="Administrador",
                hashed_password=hash_password(password),
                is_admin=True,
            )
        )
        db.commit()
        logger.info("Conta administrativa criada no bootstrap")
        return "created"
    finally:
        if owns_session:
            db.close()
