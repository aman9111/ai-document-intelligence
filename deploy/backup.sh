#!/usr/bin/env bash
# Saves a copy of the database and uploaded files into backups/<date>/ and deletes
# backups older than KEEP_DAYS. Safe to run from cron, e.g. every night at 2am:
#   0 2 * * * /home/ubuntu/ai-document-intelligence/deploy/backup.sh >> /home/ubuntu/ai-document-intelligence/backups/backup.log 2>&1
set -euo pipefail

KEEP_DAYS=7

# Run from the project folder, wherever the script is called from (cron starts in $HOME).
# docker compose reads .env (and COMPOSE_FILE in it) from here.
cd "$(dirname "$0")/.."

STAMP=$(date +%Y-%m-%d_%H-%M)
DIR="backups/$STAMP"
mkdir -p "$DIR"

echo "==> $(date '+%Y-%m-%d %H:%M:%S') backup to $DIR"

echo "    database"
docker compose exec -T db pg_dump -U app -d ai_document_intelligence | gzip > "$DIR/database.sql.gz"

echo "    uploaded files"
docker compose exec -T backend tar -czf - -C /app uploads > "$DIR/uploads.tar.gz"

ls -lh "$DIR"

echo "    removing backups older than $KEEP_DAYS days"
find backups -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -print -exec rm -rf {} +

echo "    done"
