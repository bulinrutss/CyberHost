#!/bin/bash
# Merge incremental correto: contas por telefone + analytics por conteúdo (não só id)
set -euo pipefail

LAN_DUMP="/tmp/vps_host_lan.sql"
STAGING="vps_host_lan_staging"

echo "==> Staging LAN"
sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"
sudo mariadb -e "CREATE DATABASE ${STAGING} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mariadb "$STAGING" < "$LAN_DUMP"

echo "==> Inserindo contas novas da LAN (match por telefone)"
sudo mariadb vps_host <<'SQL'
INSERT INTO users (
  phone, email, name, hashed_password, is_active, is_admin,
  mfa_secret, mfa_enabled, cloud_extra_quota_bytes, admin_pending_cloud_charge_cents,
  cloud_contracted_gb, cloud_paid_until, cloud_billing_day, cloud_monthly_cents,
  cloud_suspended_for_billing, created_at
)
SELECT
  l.phone, l.email, l.name, l.hashed_password, l.is_active, l.is_admin,
  l.mfa_secret, l.mfa_enabled, l.cloud_extra_quota_bytes, l.admin_pending_cloud_charge_cents,
  l.cloud_contracted_gb, l.cloud_paid_until, l.cloud_billing_day, l.cloud_monthly_cents,
  l.cloud_suspended_for_billing, l.created_at
FROM vps_host_lan_staging.users l
WHERE NOT EXISTS (SELECT 1 FROM users o WHERE o.phone = l.phone);
SQL

echo "==> Mapeando Samuel (LAN id 16) -> Oracle id"
SAMUEL_ORA_ID=$(sudo mariadb -N -B vps_host -e "
SELECT o.id FROM users o
JOIN vps_host_lan_staging.users l ON l.phone = o.phone
WHERE l.id = 16 LIMIT 1")
echo "Samuel oracle id = ${SAMUEL_ORA_ID}"

echo "==> Inserindo estatísticas da LAN ausentes na Oracle (novos ids automáticos)"
sudo mariadb vps_host <<SQL
INSERT INTO analytics_events (
  name, path, label, target, href, visitor_id, session_id, user_id, is_admin,
  referrer, language, timezone, ua, ua_browser, ua_os,
  viewport_w, viewport_h, duration_ms, scroll_pct, ip_hash, created_at
)
SELECT
  l.name, l.path, l.label, l.target, l.href, l.visitor_id, l.session_id,
  CASE
    WHEN l.user_id = 16 THEN ${SAMUEL_ORA_ID}
    WHEN l.user_id IS NOT NULL AND EXISTS (SELECT 1 FROM users u WHERE u.id = l.user_id) THEN l.user_id
    ELSE NULL
  END,
  l.is_admin, l.referrer, l.language, l.timezone, l.ua, l.ua_browser, l.ua_os,
  l.viewport_w, l.viewport_h, l.duration_ms, l.scroll_pct, l.ip_hash, l.created_at
FROM vps_host_lan_staging.analytics_events l
WHERE NOT EXISTS (
  SELECT 1 FROM analytics_events o
  WHERE o.name = l.name
    AND o.path = l.path
    AND o.created_at = l.created_at
    AND COALESCE(o.visitor_id, '') = COALESCE(l.visitor_id, '')
    AND COALESCE(o.user_id, -1) = COALESCE(
      CASE
        WHEN l.user_id = 16 THEN ${SAMUEL_ORA_ID}
        WHEN l.user_id IS NOT NULL AND EXISTS (SELECT 1 FROM users u WHERE u.id = l.user_id) THEN l.user_id
        ELSE NULL
      END, -1)
);
SQL

echo "==> Auth challenges da LAN (telefones novos)"
sudo mariadb vps_host <<'SQL'
INSERT IGNORE INTO auth_phone_challenges
SELECT l.* FROM vps_host_lan_staging.auth_phone_challenges l
WHERE l.phone IN (SELECT phone FROM users);

INSERT IGNORE INTO auth_email_challenges
SELECT l.* FROM vps_host_lan_staging.auth_email_challenges l
WHERE l.email IN (SELECT email FROM users WHERE email IS NOT NULL);
SQL

echo "==> VPS orders/instances novos (id inexistente)"
sudo mariadb vps_host <<SQL
INSERT IGNORE INTO vps_orders
SELECT l.* FROM vps_host_lan_staging.vps_orders l
WHERE NOT EXISTS (SELECT 1 FROM vps_orders o WHERE o.id = l.id);

INSERT IGNORE INTO vps_instances
SELECT l.* FROM vps_host_lan_staging.vps_instances l
WHERE NOT EXISTS (SELECT 1 FROM vps_instances o WHERE o.id = l.id);
SQL

sudo mariadb -e "DROP DATABASE IF EXISTS ${STAGING};"

echo "==> Resultado"
sudo mariadb vps_host <<'SQL'
SELECT 'users' t, COUNT(*) c FROM users
UNION ALL SELECT 'analytics_events', COUNT(*) FROM analytics_events
UNION ALL SELECT 'web_sites', COUNT(*) FROM web_sites
UNION ALL SELECT 'web_orders', COUNT(*) FROM web_orders;
SQL

echo "==> Usuários"
sudo mariadb -N -B vps_host -e "SELECT id, phone, name FROM users ORDER BY id"
