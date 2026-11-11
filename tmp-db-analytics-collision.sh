#!/bin/bash
STAGING="vps_host_lan_staging"
LAN_DUMP="/tmp/vps_host_lan.sql"
sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING}; CREATE DATABASE ${STAGING};"
sudo mariadb "$STAGING" < "$LAN_DUMP"

echo "=== Analytics ID collision (same id, different data) ==="
sudo mariadb -N -B vps_host -e "
SELECT COUNT(*)
FROM ${STAGING}.analytics_events l
JOIN analytics_events o ON o.id = l.id
WHERE l.path <> o.path OR l.name <> o.name OR l.created_at <> o.created_at OR COALESCE(l.user_id,0) <> COALESCE(o.user_id,0)
"

echo "=== LAN analytics not on Oracle at all (by id) ==="
sudo mariadb -N -B vps_host -e "
SELECT COUNT(*) FROM ${STAGING}.analytics_events l
LEFT JOIN analytics_events o ON o.id = l.id WHERE o.id IS NULL
"

echo "=== Sample collisions ==="
sudo mariadb -N -B vps_host -e "
SELECT l.id, l.name, l.path, l.user_id, l.created_at, '||', o.path, o.user_id, o.created_at
FROM ${STAGING}.analytics_events l
JOIN analytics_events o ON o.id = l.id
WHERE l.path <> o.path OR l.name <> o.name OR l.created_at <> o.created_at
LIMIT 15
"
