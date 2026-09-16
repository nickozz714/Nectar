#!/usr/bin/env bash
# Consistent backup of the Nectar data volume. Stops the container briefly so the
# Neo4j store is quiescent, tars the volume, starts it again.
#   ./scripts/backup.sh          -> backups/hive-data-<stamp>.tgz
#
# The volume name is ASKED TO DOCKER, never assumed. It used to be hardcoded as
# `hivemind_hive-data`, which is only right when the checkout directory happens to be
# called `HiveMind` — compose derives the project name, and therefore the volume prefix,
# from the directory. INSTALL.md tells you to clone into `Nectar/`, so the volume is
# `nectar_hive-data` there and `docker run -v hivemind_hive-data:...` would quietly CREATE
# an empty volume, tar nothing, print "backup: ..." and exit 0. A backup that reports
# success and contains no data is worse than no backup, because you stop looking.
set -euo pipefail
cd "$(dirname "$0")/.."

# -a: also find it when the stack is stopped.
CID="$(docker compose ps -aq hivemind | head -1)"
[ -n "$CID" ] || {
  echo "geen hivemind-container gevonden — draai dit vanuit de map met docker-compose.yml" >&2
  exit 1
}
VOLUME="$(docker inspect "$CID" \
  --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}')"
[ -n "$VOLUME" ] || { echo "kon het datavolume achter /data niet bepalen" >&2; exit 1; }

mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backups/hive-data-$STAMP.tgz"

echo "volume: $VOLUME"
docker compose stop
docker run --rm -v "$VOLUME":/data -v "$PWD/backups":/backup alpine \
  tar czf "/backup/hive-data-$STAMP.tgz" -C / data
docker compose start

# Een archief zonder de Neo4j-store is geen backup. Liever hier hard falen dan het
# bestand laten staan alsof het er een is.
if ! tar tzf "$OUT" | grep -q '^data/databases/'; then
  echo "backup MISLUKT: $OUT bevat geen data/databases/ — niet bruikbaar" >&2
  exit 1
fi
echo "backup: $OUT ($(du -h "$OUT" | cut -f1))"
echo "restore (container gestopt):"
echo "  docker run --rm -v $VOLUME:/data -v \"\$PWD/backups\":/backup alpine \\"
echo "    sh -c \"rm -rf /data/* && tar xzf /backup/hive-data-$STAMP.tgz -C /\""
