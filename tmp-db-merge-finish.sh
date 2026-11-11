#!/bin/bash
set -euo pipefail

LAN_DUMP="/tmp/vps_host_lan.sql"
STAGING="vps_host_lan_staging"

if ! sudo mariadb -e "USE ${STAGING}" 2>/dev/null; then
  echo "==> Recriando staging LAN"
  sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"
  sudo mariadb -e "CREATE DATABASE ${STAGING} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  sudo mariadb "$STAGING" < "$LAN_DUMP"
fi

echo "==> Merge restante (colunas compatíveis)"
sudo mariadb vps_host <<'SQL'
INSERT IGNORE INTO coupon_redemptions (id, coupon_id, order_id, user_id, created_at)
SELECT l.id, l.coupon_id, l.order_id, l.user_id, l.created_at
FROM vps_host_lan_staging.coupon_redemptions l;

INSERT IGNORE INTO support_tickets SELECT l.* FROM vps_host_lan_staging.support_tickets l;
INSERT IGNORE INTO support_messages SELECT l.* FROM vps_host_lan_staging.support_messages l;
INSERT IGNORE INTO support_mentions SELECT l.* FROM vps_host_lan_staging.support_mentions l;

INSERT IGNORE INTO auth_email_challenges SELECT l.* FROM vps_host_lan_staging.auth_email_challenges l;
INSERT IGNORE INTO auth_phone_challenges SELECT l.* FROM vps_host_lan_staging.auth_phone_challenges l;
INSERT IGNORE INTO auth_mfa_tickets SELECT l.* FROM vps_host_lan_staging.auth_mfa_tickets l;
INSERT IGNORE INTO console_ws_tickets SELECT l.* FROM vps_host_lan_staging.console_ws_tickets l;

INSERT IGNORE INTO host_push_subscriptions SELECT l.* FROM vps_host_lan_staging.host_push_subscriptions l;
INSERT IGNORE INTO billing_reminders SELECT l.* FROM vps_host_lan_staging.billing_reminders l;
SQL

sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"

echo "==> Contagens finais"
sudo mariadb vps_host <<'SQL'
SELECT 'users' t, COUNT(*) c FROM users
UNION ALL SELECT 'vps_instances', COUNT(*) FROM vps_instances
UNION ALL SELECT 'vps_orders', COUNT(*) FROM vps_orders
UNION ALL SELECT 'web_sites', COUNT(*) FROM web_sites
UNION ALL SELECT 'web_orders', COUNT(*) FROM web_orders
UNION ALL SELECT 'analytics_events', COUNT(*) FROM analytics_events
UNION ALL SELECT 'discount_coupons', COUNT(*) FROM discount_coupons
UNION ALL SELECT 'coupon_redemptions', COUNT(*) FROM coupon_redemptions;
SQL

echo "==> Reiniciando serviços"
sudo systemctl start cyberhost-backend
sleep 4
sudo systemctl start cyberhost-frontend
sudo systemctl is-active cyberhost-backend cyberhost-frontend
