#!/usr/bin/env bash
# Instalacion inicial en Ubuntu 24.04 (correr como root). Se puede repetir sin romper nada.
# El .env de produccion se copia aparte a /opt/ligapremier/backend/.env (no esta en git).
set -euo pipefail

REPO_URL="https://github.com/BrunoBlanco011/LigaPremierBackend.git"
BASE=/opt/ligapremier
APP_DIR=$BASE/backend

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip git nginx certbot python3-certbot-nginx ufw

id ligapremier >/dev/null 2>&1 || useradd --system --home-dir $BASE --shell /usr/sbin/nologin ligapremier
mkdir -p $BASE

if [ -d $APP_DIR/.git ]; then
    git -C $APP_DIR pull --ff-only
else
    git clone $REPO_URL $APP_DIR
fi

[ -d $BASE/venv ] || python3 -m venv $BASE/venv
$BASE/venv/bin/pip install --upgrade pip
$BASE/venv/bin/pip install -r $APP_DIR/requirements.txt

chown -R ligapremier:ligapremier $BASE
[ -f $APP_DIR/.env ] && chmod 600 $APP_DIR/.env

install -m 644 $APP_DIR/deploy/ligapremier-api.service /etc/systemd/system/ligapremier-api.service
install -m 644 $APP_DIR/deploy/nginx-ligapremier.conf /etc/nginx/sites-available/ligapremier
ln -sf /etc/nginx/sites-available/ligapremier /etc/nginx/sites-enabled/ligapremier
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload-or-restart nginx
systemctl enable nginx

systemctl daemon-reload
systemctl enable ligapremier-api
if [ -f $APP_DIR/.env ]; then
    systemctl restart ligapremier-api
else
    echo "Falta $APP_DIR/.env: copialo y corre 'systemctl restart ligapremier-api'"
fi

ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
