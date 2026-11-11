"""
Cria o banco MariaDB vps_host (zerado) e as tabelas.
Uso: cd backend && python scripts/init_mariadb.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database_bootstrap import ensure_mariadb_database
from app.database import Base, engine
from app.main import seed_default_plan
from app.services.admin_bootstrap import seed_admin_user


def main() -> None:
    ensure_mariadb_database()
    Base.metadata.create_all(bind=engine)
    seed_admin_user()
    seed_default_plan()
    print("Banco vps_host criado e inicializado com sucesso.")


if __name__ == "__main__":
    main()
