#!/bin/bash
echo "=== SSL server blocks ==="
sudo nginx -T 2>/dev/null | grep -A2 'listen.*443'

echo "=== Web sites DB ==="
sudo mariadb vps_host -e "SELECT id, site_slug, domain, status FROM web_sites;"

echo "=== nginx path snippets ==="
ls -la /opt/host/data/web_sites/nginx/paths/ 2>/dev/null || echo none
ls -la /opt/host/data/web_sites/nginx/domains/ 2>/dev/null || echo none

echo "=== /var/www/ruts index head ==="
head -5 /var/www/ruts/index.html 2>/dev/null || echo missing

echo "=== sites-enabled ==="
ls -la /etc/nginx/sites-enabled/
