#!/usr/bin/env bash
# Actualiza el servidor con lo ultimo de main (correr como root)
set -euo pipefail

BASE=/opt/ligapremier
APP_DIR=$BASE/backend

sudo -u ligapremier git -C $APP_DIR pull --ff-only
sudo -u ligapremier $BASE/venv/bin/pip install -r $APP_DIR/requirements.txt
systemctl restart ligapremier-api
sleep 2
curl -fsS -H "Host: localhost" http://127.0.0.1:8000/health && echo
