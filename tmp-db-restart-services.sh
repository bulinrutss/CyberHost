#!/bin/bash
set -euo pipefail
STAGING="vps_host_lan_staging"
sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};" 2>/dev/null || true

echo "==> Contagens finais"
sudo mariadb vps_host <<'SQL'
SELECT 'users' t, COUNT(*) c FROM users
UNION ALL SELECT 'vps_instances', COUNT(*) FROM vps_instances
UNION ALL SELECT 'vps_orders', COUNT(*) FROM vps_orders
UNION ALL SELECT 'web_sites', COUNT(*) FROM web_sites
UNION ALL SELECT 'web_orders', COUNT(*) FROM web_orders
UNION ALL SELECT 'analytics_events', COUNT(*) FROM analytics_events
UNION ALL SELECT 'discount_coupons', COUNT(*) FROM discount_coupons;
SQL

echo "==> Reiniciando serviços"
sudo systemctl start cyberhost-backend
sleep 4
sudo systemctl start cyberhost-frontend
sleep 2
sudo systemctl is-active cyberhost-backend cyberhost-frontend
curl -s -o /dev/null -w "api=%{http_code}\n" http://127.0.0.1:8810/api/vps/plans
