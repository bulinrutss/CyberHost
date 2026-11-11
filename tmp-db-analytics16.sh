#!/bin/bash
STAGING="vps_host_lan_staging"
echo "=== LAN analytics user_id=16 ==="
sudo mariadb -N -B "$STAGING" -e "SELECT id, name, path, user_id, created_at FROM analytics_events WHERE user_id=16 ORDER BY id"

echo "=== Oracle analytics same ids ==="
sudo mariadb -N -B vps_host -e "
SELECT o.id, o.name, o.path, o.user_id, o.created_at
FROM analytics_events o
WHERE o.id IN (SELECT id FROM ${STAGING}.analytics_events WHERE user_id=16)
ORDER BY o.id"
