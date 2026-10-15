#!/usr/bin/env bash
# Actualiza el servidor con lo ultimo de main (correr como root)
set -euo pipefail

BASE=/opt/ligapremier
APP_DIR=$BASE/backend

sudo -u ligapremier git -C $APP_DIR pull --ff-only
sudo -u ligapremier $BASE/venv/bin/pip install -r $APP_DIR/requirements.txt
systemctl restart ligapremier-api

# La API tarda unos segundos en levantar: reintentar hasta 30 s antes de fallar
for _ in $(seq 1 30); do
    if curl -fs -H "Host: localhost" http://127.0.0.1:8000/health; then
        echo
        exit 0
    fi
    sleep 1
done
echo "La API no respondio en /health tras 30 s; revisa: journalctl -u ligapremier-api -n 50" >&2
exit 1
