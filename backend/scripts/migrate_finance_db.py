"""Copia dados do Financeiro de vps_host → financeiro.

IMPORTANTE: NÃO apaga nem altera usuários no CyberHost (vps_host.users).
Apenas COPY para o banco financeiro.
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _create_db_if_needed(url_str: str) -> None:
    url = make_url(url_str)
    if not url.drivername.startswith("mysql"):
        return
    import pymysql

    conn = pymysql.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def _user_ids(src, explicit: list[int] | None) -> list[int]:
    if explicit:
        return sorted(set(explicit))
    rows = src.execute(
        text(
            """
            SELECT id FROM (
              SELECT DISTINCT user_id AS id FROM finance_transactions
              UNION SELECT DISTINCT user_id FROM finance_goals
              UNION SELECT DISTINCT user_id FROM finance_events
              UNION SELECT DISTINCT user_id FROM finance_push_subscriptions
              UNION SELECT id FROM users WHERE LOWER(name) LIKE '%luciano%'
            ) t
            """
        )
    ).fetchall()
    return sorted({int(r[0]) for r in rows})


def migrate(source_url: str, dest_url: str, user_ids: list[int] | None) -> None:
    _create_db_if_needed(dest_url)

    from app.finance_database import FinanceBase, _make_engine
    import app.models.finance  # noqa: F401
    import app.models.finance_auth  # noqa: F401
    import app.models.finance_user  # noqa: F401

    dest_engine = _make_engine(dest_url)
    FinanceBase.metadata.create_all(bind=dest_engine)
    src_engine = create_engine(source_url, pool_pre_ping=True)

    with src_engine.connect() as src, dest_engine.begin() as dst:
        ids = _user_ids(src, user_ids)
        if not ids:
            print("Nenhum usuário para migrar.")
            return
        print(f"Copiando user_ids={ids} (somente COPY; CyberHost intacto)")
        id_params = {f"id{i}": uid for i, uid in enumerate(ids)}
        id_list = ", ".join(f":id{i}" for i in range(len(ids)))

        # users → subset FinanceUser (MFA limpo)
        users = src.execute(
            text(
                f"SELECT id, phone, email, name, hashed_password, is_active, created_at "
                f"FROM users WHERE id IN ({id_list})"
            ),
            id_params,
        ).mappings().all()
        for u in users:
            dst.execute(
                text(
                    "REPLACE INTO users "
                    "(id, phone, email, name, hashed_password, is_active, "
                    " mfa_secret, mfa_enabled, created_at) "
                    "VALUES (:id, :phone, :email, :name, :hashed_password, :is_active, "
                    " NULL, 0, :created_at)"
                ),
                dict(u),
            )
        print(f"  users: {len(users)}")

        for table in (
            "finance_transactions",
            "finance_goals",
            "finance_events",
            "finance_push_subscriptions",
        ):
            cols = [r[0] for r in src.execute(text(f"SHOW COLUMNS FROM `{table}`")).fetchall()]
            col_list = ", ".join(f"`{c}`" for c in cols)
            ph = ", ".join(f":{c}" for c in cols)
            rows = src.execute(
                text(f"SELECT {col_list} FROM `{table}` WHERE user_id IN ({id_list})"),
                id_params,
            ).mappings().all()
            for row in rows:
                dst.execute(
                    text(f"REPLACE INTO `{table}` ({col_list}) VALUES ({ph})"),
                    dict(row),
                )
            print(f"  {table}: {len(rows)}")

        # notices by event ownership
        cols = [
            r[0]
            for r in src.execute(text("SHOW COLUMNS FROM finance_event_notices")).fetchall()
        ]
        col_list = ", ".join(f"`{c}`" for c in cols)
        ph = ", ".join(f":{c}" for c in cols)
        rows = src.execute(
            text(
                f"SELECT n.* FROM finance_event_notices n "
                f"JOIN finance_events e ON e.id = n.event_id "
                f"WHERE e.user_id IN ({id_list})"
            ),
            id_params,
        ).mappings().all()
        for row in rows:
            dst.execute(
                text(f"REPLACE INTO finance_event_notices ({col_list}) VALUES ({ph})"),
                dict(row),
            )
        print(f"  finance_event_notices: {len(rows)}")

    print("OK — CyberHost (vps_host.users) NÃO foi alterado.")
    src_engine.dispose()
    dest_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--dest-url", default="")
    parser.add_argument("--user-ids", default="")
    args = parser.parse_args()

    from app.config import get_settings

    settings = get_settings()
    source = args.source_url or settings.database_url
    dest = args.dest_url or settings.resolved_finance_database_url
    ids = (
        [int(x.strip()) for x in args.user_ids.split(",") if x.strip()]
        if args.user_ids
        else None
    )
    print(f"source db={make_url(source).database} → dest db={make_url(dest).database}")
    migrate(source, dest, ids)


if __name__ == "__main__":
    main()
