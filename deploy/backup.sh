#!/usr/bin/env bash
# Saves a copy of the database and uploaded files into ./backups/<date>/.
# Run from the project folder:  bash deploy/backup.sh
set -euo pipefail

STAMP=$(date +%Y-%m-%d_%H-%M)
DIR="backups/$STAMP"
mkdir -p "$DIR"

echo "==> Database"
docker compose exec -T db pg_dump -U app -d ai_document_intelligence | gzip > "$DIR/database.sql.gz"

echo "==> Uploaded files"
docker compose exec -T backend tar -czf - -C /app uploads > "$DIR/uploads.tar.gz"

echo "Saved to $DIR"
ls -lh "$DIR"
