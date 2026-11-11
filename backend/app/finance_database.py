"""Banco isolado do Financeiro (schema `financeiro`)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class FinanceBase(DeclarativeBase):
    pass


def _url() -> str:
    return get_settings().resolved_finance_database_url


def _make_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


finance_engine = _make_engine(_url())
FinanceSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=finance_engine)


def get_finance_db():
    db = FinanceSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_finance_db() -> None:
    # Import models so metadata is populated.
    import app.models.finance  # noqa: F401
    import app.models.finance_auth  # noqa: F401
    import app.models.finance_user  # noqa: F401

    FinanceBase.metadata.create_all(bind=finance_engine)


def reset_finance_engine_for_tests(url: str):
    """Recria engine/session para testes com SQLite em memória."""
    global finance_engine, FinanceSessionLocal
    finance_engine.dispose()
    finance_engine = _make_engine(url)
    FinanceSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=finance_engine
    )
