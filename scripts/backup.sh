#!/usr/bin/env bash
# Back up the HC Tracker site (database + public/private files + site config) to ./backups
# Usage: ./scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

docker compose exec -T backend bench --site "$SITE_NAME" backup --with-files
mkdir -p backups
SITE_DIR="/home/frappe/frappe-bench/sites/$SITE_NAME/private/backups"
docker compose cp "backend:$SITE_DIR/." ./backups/
echo "Backups copied to $(pwd)/backups:"
ls -lt backups | head -n 6
