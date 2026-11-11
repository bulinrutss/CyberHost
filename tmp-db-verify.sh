#!/bin/bash
sudo mariadb vps_host <<'SQL'
SELECT 'users' t, COUNT(*) c FROM users
UNION ALL SELECT 'vps_instances', COUNT(*) FROM vps_instances
UNION ALL SELECT 'vps_orders', COUNT(*) FROM vps_orders
UNION ALL SELECT 'cloud_storage_orders', COUNT(*) FROM cloud_storage_orders
UNION ALL SELECT 'cloud_files', COUNT(*) FROM cloud_files
UNION ALL SELECT 'analytics_events', COUNT(*) FROM analytics_events
UNION ALL SELECT 'web_sites', COUNT(*) FROM web_sites
UNION ALL SELECT 'web_orders', COUNT(*) FROM web_orders
UNION ALL SELECT 'web_plan_presets', COUNT(*) FROM web_plan_presets;
SQL
