#!/usr/bin/env bash
# Consistent backup of the HiveMind data volume. Stops the container briefly so the
# Neo4j store is quiescent, tars the volume, starts it again.
#   ./scripts/backup.sh          -> backups/hive-data-<stamp>.tgz
# Restore (container stopped):
#   docker run --rm -v hivemind_hive-data:/data -v "$PWD/backups":/backup alpine \
#     sh -c "rm -rf /data/* && tar xzf /backup/<file>.tgz -C /"
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
docker compose stop
docker run --rm -v hivemind_hive-data:/data -v "$PWD/backups":/backup alpine \
  tar czf "/backup/hive-data-$STAMP.tgz" -C / data
docker compose start
echo "backup: backups/hive-data-$STAMP.tgz"
