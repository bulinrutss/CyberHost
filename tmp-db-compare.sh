#!/bin/bash
set -euo pipefail

MYSQL="sudo mariadb"
{
  echo "=== HOST $(hostname) ==="
  $MYSQL -N -e "SELECT VERSION();" vps_host
  echo "=== TABLES ==="
  $MYSQL -N -e "
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema='vps_host' AND table_type='BASE TABLE'
    ORDER BY table_name;
  " vps_host
  echo "=== ROW_COUNTS ==="
  $MYSQL -N -e "
    SELECT table_name, IFNULL(table_rows,0)
    FROM information_schema.tables
    WHERE table_schema='vps_host' AND table_type='BASE TABLE'
    ORDER BY table_name;
  " vps_host
  echo "=== COLUMNS ==="
  $MYSQL -N -e "
    SELECT table_name, column_name, column_type, is_nullable, column_default, extra
    FROM information_schema.columns
    WHERE table_schema='vps_host'
    ORDER BY table_name, ordinal_position;
  " vps_host
}
