#!/bin/bash
# Restaura vps_host da LAN (.105) na Oracle — executar NA ORACLE como ubuntu.
set -euo pipefail

DUMP="/tmp/vps_host_lan.sql"
BACKUP="/tmp/vps_host_oracle_backup_$(date +%Y%m%d_%H%M%S).sql"

if [[ ! -f "$DUMP" ]]; then
  echo "ERRO: dump não encontrado em $DUMP"
  exit 1
fi

echo "==> Backup Oracle atual em $BACKUP"
sudo mysqldump --single-transaction --routines --triggers vps_host > "$BACKUP"

echo "==> Parando serviços"
sudo systemctl stop cyberhost-frontend cyberhost-backend || true
sleep 2

echo "==> Recriando banco vps_host"
sudo mariadb -e "DROP DATABASE IF EXISTS vps_host;"
sudo mariadb -e "CREATE DATABASE vps_host CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "==> Importando dump da LAN"
sudo mariadb vps_host < "$DUMP"

echo "==> Reaplicando permissões do usuário da aplicação"
DB_USER=$(sudo grep '^DATABASE_URL=' /opt/host/backend/.env | sed -n 's#mysql+pymysql://\([^:]*\):.*#\1#p')
if [[ -n "$DB_USER" && "$DB_USER" != "root" ]]; then
  sudo mariadb -e "GRANT ALL PRIVILEGES ON vps_host.* TO '${DB_USER}'@'localhost'; FLUSH PRIVILEGES;" || true
  sudo mariadb -e "GRANT ALL PRIVILEGES ON vps_host.* TO '${DB_USER}'@'127.0.0.1'; FLUSH PRIVILEGES;" || true
fi

echo "==> Reiniciando backend (migrations + seeds)"
sudo systemctl start cyberhost-backend
sleep 5
sudo systemctl is-active cyberhost-backend

echo "==> Reiniciando frontend"
sudo systemctl start cyberhost-frontend
sleep 2
sudo systemctl is-active cyberhost-frontend

echo "==> Tabelas após import:"
sudo mariadb -N -e "SHOW TABLES;" vps_host | wc -l

echo "OK: importação concluída. Backup Oracle em $BACKUP"
