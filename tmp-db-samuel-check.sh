#!/bin/bash
set -euo pipefail
STAGING="vps_host_lan_staging"
LAN_DUMP="/tmp/vps_host_lan.sql"

sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"
sudo mariadb -e "CREATE DATABASE ${STAGING} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mariadb "$STAGING" < "$LAN_DUMP"

echo "=== Samuel (LAN user 16) related data ==="
sudo mariadb -N -B vps_host -e "
SELECT 'vps_orders' t, COUNT(*) FROM ${STAGING}.vps_orders WHERE user_id=16
UNION ALL SELECT 'vps_instances', COUNT(*) FROM ${STAGING}.vps_instances WHERE user_id=16
UNION ALL SELECT 'analytics_user', COUNT(*) FROM ${STAGING}.analytics_events WHERE user_id=16
UNION ALL SELECT 'game_orders', COUNT(*) FROM ${STAGING}.game_orders WHERE user_id=16
UNION ALL SELECT 'cloud_files', COUNT(*) FROM ${STAGING}.cloud_files WHERE user_id=16
UNION ALL SELECT 'cloud_orders', COUNT(*) FROM ${STAGING}.cloud_storage_orders WHERE user_id=16
UNION ALL SELECT 'finance_tx', COUNT(*) FROM ${STAGING}.finance_transactions WHERE user_id=16
"

echo "=== Murilo (Oracle user 16) ==="
sudo mariadb -N -B vps_host -e "
SELECT 'vps_orders' t, COUNT(*) FROM vps_orders WHERE user_id=16
UNION ALL SELECT 'vps_instances', COUNT(*) FROM vps_instances WHERE user_id=16
UNION ALL SELECT 'analytics_user', COUNT(*) FROM analytics_events WHERE user_id=16
"

echo "=== Next free user id ==="
sudo mariadb -N -B vps_host -e "SELECT COALESCE(MAX(id),0)+1 FROM users"

echo "=== LAN vps_orders user 16 ==="
sudo mariadb -N -B "$STAGING" -e "SELECT id, user_id, hostname, status, total_cents FROM vps_orders WHERE user_id=16"

echo "=== Users only on LAN ==="
sudo mariadb -N -B vps_host -e "
SELECT l.id, l.phone, l.name, l.email
FROM ${STAGING}.users l
LEFT JOIN users o ON o.phone = l.phone
WHERE o.id IS NULL"
