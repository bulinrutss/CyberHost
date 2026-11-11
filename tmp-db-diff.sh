#!/bin/bash
set -euo pipefail
LAN_DUMP="/tmp/vps_host_lan.sql"
STAGING="vps_host_lan_staging"

sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"
sudo mariadb -e "CREATE DATABASE ${STAGING} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mariadb "$STAGING" < "$LAN_DUMP"

echo "=== USERS LAN (phone, id, name) ==="
sudo mariadb -N -B "$STAGING" -e "SELECT id, phone, COALESCE(email,''), name FROM users ORDER BY id"

echo "=== USERS ORACLE ==="
sudo mariadb -N -B vps_host -e "SELECT id, phone, COALESCE(email,''), name FROM users ORDER BY id"

echo "=== ONLY ON LAN (by phone) ==="
sudo mariadb -N -B vps_host -e "
SELECT l.id, l.phone, l.name
FROM ${STAGING}.users l
LEFT JOIN users o ON o.phone = l.phone
WHERE o.id IS NULL
ORDER BY l.id"

echo "=== ONLY ON ORACLE (by phone) ==="
sudo mariadb -N -B vps_host -e "
SELECT o.id, o.phone, o.name
FROM users o
LEFT JOIN ${STAGING}.users l ON l.phone = o.phone
WHERE l.id IS NULL
ORDER BY o.id"

echo "=== VPS INSTANCES LAN ==="
sudo mariadb -N -B "$STAGING" -e "SELECT id, user_id, vm_name, status FROM vps_instances ORDER BY id"

echo "=== VPS INSTANCES ORACLE ==="
sudo mariadb -N -B vps_host -e "SELECT id, user_id, vm_name, status FROM vps_instances ORDER BY id"

echo "=== ANALYTICS COUNTS ==="
sudo mariadb -N -B vps_host -e "SELECT 'lan', COUNT(*) FROM ${STAGING}.analytics_events UNION ALL SELECT 'oracle', COUNT(*) FROM analytics_events"

echo "=== ANALYTICS ONLY ON LAN (by id) ==="
sudo mariadb -N -B vps_host -e "
SELECT COUNT(*) FROM ${STAGING}.analytics_events l
LEFT JOIN analytics_events o ON o.id = l.id
WHERE o.id IS NULL"
