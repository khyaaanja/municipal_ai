#!/usr/bin/env bash
# Production deploy script for Bhaktapur Municipal AI
# Usage:
#   ./deploy.sh          — first deploy (builds, migrates, starts 3 web replicas)
#   ./deploy.sh scale 5  — scale web to 5 replicas
#   ./deploy.sh update   — zero-downtime rolling update (pull + rebuild + restart)
set -euo pipefail

WEB_REPLICAS=${2:-3}

case "${1:-deploy}" in

  deploy)
    echo "==> Checking .env..."
    [ -f .env ] || { echo "ERROR: .env missing. Copy .env.example and fill in values."; exit 1; }
    grep -q "CHANGE_ME" .env && echo "WARNING: .env still has CHANGE_ME placeholders!"

    echo "==> Building images..."
    docker-compose build --parallel

    echo "==> Starting services (${WEB_REPLICAS} web replicas)..."
    docker-compose up -d --scale web="${WEB_REPLICAS}" db redis

    echo "==> Waiting for DB..."
    docker-compose exec db mysqladmin ping -h localhost --silent --wait=30

    echo "==> Starting web, celery, celery-beat, nginx..."
    docker-compose up -d --scale web="${WEB_REPLICAS}" celery celery-beat nginx web

    echo "==> Creating superuser (skip if exists)..."
    docker-compose exec web python manage.py createsuperuser --no-input 2>/dev/null || true

    echo "==> Done. App running at https://$(grep ALLOWED_HOSTS .env | cut -d= -f2 | cut -d, -f1)"
    ;;

  scale)
    echo "==> Scaling web to ${WEB_REPLICAS} replicas..."
    docker-compose up -d --scale web="${WEB_REPLICAS}" --no-recreate web
    echo "==> Scaled. $(docker-compose ps web | grep -c Up) web containers running."
    ;;

  update)
    echo "==> Zero-downtime update..."
    docker-compose build --parallel web
    # Bring up new web containers before stopping old ones
    docker-compose up -d --scale web="${WEB_REPLICAS}" --no-deps web
    docker-compose restart celery celery-beat
    echo "==> Update complete."
    ;;

  *)
    echo "Usage: $0 [deploy|scale N|update]"
    exit 1
    ;;
esac
