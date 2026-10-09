#!/usr/bin/env bash
# Restore the HC Tracker site from a backup set in ./backups
# Usage: ./scripts/restore.sh <timestamp-prefix>      e.g. ./scripts/restore.sh 20261009_183250
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

PREFIX="${1:?Pass the backup timestamp prefix, e.g. 20261009_183250}"
DB=$(ls backups/${PREFIX}*-database.sql.gz | head -n1)
PUB=$(ls backups/${PREFIX}*-files.tar 2>/dev/null | grep -v private-files | head -n1 || true)
PRIV=$(ls backups/${PREFIX}*-private-files.tar 2>/dev/null | head -n1 || true)

docker compose exec -T -u root backend rm -rf /tmp/restore
docker compose exec -T backend mkdir -p /tmp/restore
docker compose cp "$DB" backend:/tmp/restore/
ARGS=(/tmp/restore/$(basename "$DB"))
if [ -n "$PUB" ]; then docker compose cp "$PUB" backend:/tmp/restore/; ARGS+=(--with-public-files "/tmp/restore/$(basename "$PUB")"); fi
if [ -n "$PRIV" ]; then docker compose cp "$PRIV" backend:/tmp/restore/; ARGS+=(--with-private-files "/tmp/restore/$(basename "$PRIV")"); fi

docker compose exec -T backend bench --site "$SITE_NAME" restore "${ARGS[@]}" \
  --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" --force
docker compose exec -T backend bench --site "$SITE_NAME" migrate
docker compose exec -T backend bench --site "$SITE_NAME" scheduler enable
docker compose exec -T -u root backend rm -rf /tmp/restore
echo "Restore of $PREFIX finished."
