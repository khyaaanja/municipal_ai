#!/usr/bin/env bash
# Nightly database backup.
#
# There was no backup and no binary logging when the database was wiped on
# 2026-09-15, which is why the citizen complaints in it were unrecoverable.
# Schema and seeded content can be rebuilt from the importers; filed
# complaints and real accounts cannot.
#
# Install:  crontab -e
#   15 2 * * *  /home/kali-linux/Desktop/municipal_ai/scripts/backup_db.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${MUNICIPAL_AI_BACKUP_DIR:-$HOME/backups/municipal_ai}"
KEEP_DAYS="${MUNICIPAL_AI_BACKUP_KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

# Credentials come from Django's settings so they are never duplicated here
# and never appear in the process list.
read -r DB_NAME DB_USER DB_HOST DB_PORT <<<"$(
  cd "$PROJECT_DIR" && \
  "${PYTHON_BIN:-$PROJECT_DIR/venv/bin/python}" -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'municipal_ai.settings')
django.setup()
from django.conf import settings
d = settings.DATABASES['default']
print(d['NAME'], d['USER'], d['HOST'] or 'localhost', d['PORT'] or '3306')
")"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/${DB_NAME}-${STAMP}.sql.gz"

# --defaults-file keeps the password out of argv, where `ps` would show it.
CNF="$(mktemp)"
trap 'rm -f "$CNF"' EXIT
chmod 600 "$CNF"
{
  echo "[client]"
  echo "user=${DB_USER}"
  printf 'password=%s\n' "$(cd "$PROJECT_DIR" && "${PYTHON_BIN:-$PROJECT_DIR/venv/bin/python}" -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'municipal_ai.settings')
django.setup()
from django.conf import settings
print(settings.DATABASES['default']['PASSWORD'])
")"
  echo "host=${DB_HOST}"
  echo "port=${DB_PORT}"
} > "$CNF"

mariadb-dump --defaults-file="$CNF" \
  --single-transaction --quick --routines --triggers --events \
  "$DB_NAME" | gzip -9 > "$OUT"

# A dump that failed midway is worse than none, because it looks like a backup.
if ! gzip -t "$OUT" 2>/dev/null; then
  echo "backup failed verification, removing: $OUT" >&2
  rm -f "$OUT"
  exit 1
fi

find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -mtime "+${KEEP_DAYS}" -delete
echo "$(date -Is) ok $(du -h "$OUT" | cut -f1) $OUT"
