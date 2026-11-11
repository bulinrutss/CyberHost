#!/bin/bash
# 1) Restaura backup Oracle  2) Importa LAN em staging  3) Merge incremental
set -euo pipefail

ORACLE_BACKUP="/tmp/vps_host_oracle_backup_20260902_220651.sql"
LAN_DUMP="/tmp/vps_host_lan.sql"
STAGING="vps_host_lan_staging"

if [[ ! -f "$ORACLE_BACKUP" || ! -f "$LAN_DUMP" ]]; then
  echo "ERRO: backup ou dump LAN ausente"
  exit 1
fi

echo "==> Parando serviços"
sudo systemctl stop cyberhost-frontend cyberhost-backend || true
sleep 2

echo "==> Restaurando backup Oracle (estado anterior)"
sudo mariadb -e "DROP DATABASE IF EXISTS vps_host;"
sudo mariadb -e "CREATE DATABASE vps_host CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mariadb vps_host < "$ORACLE_BACKUP"

echo "==> Staging LAN"
sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"
sudo mariadb -e "CREATE DATABASE ${STAGING} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mariadb "$STAGING" < "$LAN_DUMP"

echo "==> Merge incremental (Oracle base + extras da LAN)"
sudo mariadb vps_host <<'SQL'
-- Usuários novos na LAN (por telefone)
INSERT INTO users (
  id, phone, email, name, hashed_password, is_active, is_admin,
  mfa_secret, mfa_enabled, cloud_extra_quota_bytes, admin_pending_cloud_charge_cents,
  cloud_contracted_gb, cloud_paid_until, cloud_billing_day, cloud_monthly_cents,
  cloud_suspended_for_billing, created_at
)
SELECT l.id, l.phone, l.email, l.name, l.hashed_password, l.is_active, l.is_admin,
  l.mfa_secret, l.mfa_enabled, l.cloud_extra_quota_bytes, l.admin_pending_cloud_charge_cents,
  l.cloud_contracted_gb, l.cloud_paid_until, l.cloud_billing_day, l.cloud_monthly_cents,
  l.cloud_suspended_for_billing, l.created_at
FROM vps_host_lan_staging.users l
LEFT JOIN users o ON o.phone = l.phone
WHERE o.id IS NULL
  AND NOT EXISTS (SELECT 1 FROM users x WHERE x.id = l.id);

-- Analytics: eventos da LAN que ainda não existem na Oracle (por id)
INSERT IGNORE INTO analytics_events
SELECT l.* FROM vps_host_lan_staging.analytics_events l;

-- Auth throttle: entradas novas
INSERT IGNORE INTO auth_throttle
SELECT l.* FROM vps_host_lan_staging.auth_throttle l;

-- VPS orders novos (id inexistente na Oracle)
INSERT IGNORE INTO vps_orders
SELECT l.* FROM vps_host_lan_staging.vps_orders l;

-- VPS instances novas
INSERT IGNORE INTO vps_instances
SELECT l.* FROM vps_host_lan_staging.vps_instances l;

-- Planos/presets (se faltar algum)
INSERT IGNORE INTO vps_plans SELECT l.* FROM vps_host_lan_staging.vps_plans l;
INSERT IGNORE INTO vps_plan_presets SELECT l.* FROM vps_host_lan_staging.vps_plan_presets l;
INSERT IGNORE INTO game_plan_presets SELECT l.* FROM vps_host_lan_staging.game_plan_presets l;

-- Game orders/servers
INSERT IGNORE INTO game_orders SELECT l.* FROM vps_host_lan_staging.game_orders l;
INSERT IGNORE INTO game_servers SELECT l.* FROM vps_host_lan_staging.game_servers l;
INSERT IGNORE INTO game_hosts SELECT l.* FROM vps_host_lan_staging.game_hosts l;

-- Cloud
INSERT IGNORE INTO cloud_files SELECT l.* FROM vps_host_lan_staging.cloud_files l;
INSERT IGNORE INTO cloud_file_chunks SELECT l.* FROM vps_host_lan_staging.cloud_file_chunks l;
INSERT IGNORE INTO cloud_storage_orders SELECT l.* FROM vps_host_lan_staging.cloud_storage_orders l;
INSERT IGNORE INTO cloud_discord_tombstones SELECT l.* FROM vps_host_lan_staging.cloud_discord_tombstones l;

-- Financeiro
INSERT IGNORE INTO finance_events SELECT l.* FROM vps_host_lan_staging.finance_events l;
INSERT IGNORE INTO finance_transactions SELECT l.* FROM vps_host_lan_staging.finance_transactions l;
INSERT IGNORE INTO finance_goals SELECT l.* FROM vps_host_lan_staging.finance_goals l;
INSERT IGNORE INTO finance_event_notices SELECT l.* FROM vps_host_lan_staging.finance_event_notices l;
INSERT IGNORE INTO finance_push_subscriptions SELECT l.* FROM vps_host_lan_staging.finance_push_subscriptions l;

-- Cupons (só se id novo)
INSERT IGNORE INTO discount_coupons SELECT l.* FROM vps_host_lan_staging.discount_coupons l;
INSERT IGNORE INTO coupon_redemptions SELECT l.* FROM vps_host_lan_staging.coupon_redemptions l;

-- Suporte
INSERT IGNORE INTO support_tickets SELECT l.* FROM vps_host_lan_staging.support_tickets l;
INSERT IGNORE INTO support_messages SELECT l.* FROM vps_host_lan_staging.support_messages l;
INSERT IGNORE INTO support_mentions SELECT l.* FROM vps_host_lan_staging.support_mentions l;

-- Auth challenges/tickets
INSERT IGNORE INTO auth_email_challenges SELECT l.* FROM vps_host_lan_staging.auth_email_challenges l;
INSERT IGNORE INTO auth_phone_challenges SELECT l.* FROM vps_host_lan_staging.auth_phone_challenges l;
INSERT IGNORE INTO auth_mfa_tickets SELECT l.* FROM vps_host_lan_staging.auth_mfa_tickets l;
INSERT IGNORE INTO console_ws_tickets SELECT l.* FROM vps_host_lan_staging.console_ws_tickets l;

-- Push
INSERT IGNORE INTO host_push_subscriptions SELECT l.* FROM vps_host_lan_staging.host_push_subscriptions l;

-- Billing reminders
INSERT IGNORE INTO billing_reminders SELECT l.* FROM vps_host_lan_staging.billing_reminders l;
SQL

echo "==> Contagens pós-merge"
sudo mariadb vps_host <<'SQL'
SELECT 'users' t, COUNT(*) c FROM users
UNION ALL SELECT 'vps_instances', COUNT(*) FROM vps_instances
UNION ALL SELECT 'vps_orders', COUNT(*) FROM vps_orders
UNION ALL SELECT 'web_sites', COUNT(*) FROM web_sites
UNION ALL SELECT 'web_orders', COUNT(*) FROM web_orders
UNION ALL SELECT 'analytics_events', COUNT(*) FROM analytics_events
UNION ALL SELECT 'discount_coupons', COUNT(*) FROM discount_coupons;
SQL

echo "==> Limpando staging"
sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"

echo "==> Reiniciando serviços"
sudo systemctl start cyberhost-backend
sleep 4
sudo systemctl start cyberhost-frontend
sudo systemctl is-active cyberhost-backend cyberhost-frontend

echo "OK: Oracle restaurada + merge incremental da LAN"
