#!/usr/bin/env bash
# Daily MySQL backup — run via cron: 0 2 * * * /path/to/backup_db.sh
set -euo pipefail

BACKUP_DIR="/backups/municipal_ai"
DATE=$(date +%Y%m%d_%H%M%S)
DAYS_TO_KEEP=30

# Load .env if running outside Docker
if [ -f "$(dirname "$0")/../.env" ]; then
    export $(grep -v '^#' "$(dirname "$0")/../.env" | xargs)
fi

DB_NAME="${DB_NAME:-municipal_ai_db}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"

mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/db_${DATE}.sql.gz"

echo "[$(date)] Starting backup of $DB_NAME..."
mysqldump \
    -h "$DB_HOST" \
    -u "$DB_USER" \
    -p"$DB_PASSWORD" \
    --single-transaction \
    --routines \
    --triggers \
    "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup saved: $BACKUP_FILE ($(du -sh "$BACKUP_FILE" | cut -f1))"

# Remove backups older than DAYS_TO_KEEP days
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +"$DAYS_TO_KEEP" -delete
echo "[$(date)] Old backups pruned (kept last $DAYS_TO_KEEP days)"

# Optional: sync to remote storage (uncomment and configure)
# rsync -az "$BACKUP_DIR/" user@remote-server:/backups/municipal_ai/
# aws s3 sync "$BACKUP_DIR/" s3://your-bucket/backups/
