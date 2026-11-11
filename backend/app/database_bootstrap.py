"""Cria o banco MariaDB antes da primeira conexão da aplicação."""

from __future__ import annotations

import logging

import pymysql
from sqlalchemy.engine import make_url

from app.config import get_settings

logger = logging.getLogger(__name__)


def ensure_mariadb_database() -> None:
    settings = get_settings()
    urls = [settings.database_url, settings.resolved_finance_database_url]
    seen: set[str] = set()
    for raw in urls:
        url = make_url(raw)
        if not url.drivername.startswith("mysql"):
            continue
        database = url.database
        if not database or database in seen:
            continue
        seen.add(database)
        connection = pymysql.connect(
            host=url.host or "127.0.0.1",
            port=url.port or 3306,
            user=url.username or "root",
            password=url.password or "",
            charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            connection.commit()
        finally:
            connection.close()
        logger.info("Banco MariaDB '%s' pronto", database)
