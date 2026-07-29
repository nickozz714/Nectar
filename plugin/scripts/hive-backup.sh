#!/usr/bin/env bash
# Back-up & restore of the whole hive over plain HTTP (same transport as the recall hook).
# org_admin token required.
#
#   hive-backup.sh export [file.json]        download a full snapshot (default: hivemind-backup-<ts>.json)
#   hive-backup.sh import <file.json>        restore, upserting (merge) into the org
#   hive-backup.sh import <file.json> replace   wipe the org's knowledge first, then restore
#
# HIVE_URL/HIVE_TOKEN are read from env → ~/.hivemind/config.json → this project's
# .claude/settings.json (same resolution as the other hive scripts).
set -uo pipefail

PROJECT="$(pwd)"
SETTINGS="$PROJECT/.claude/settings.json"
CFG="$HOME/.hivemind/config.json"

if [ -z "${HIVE_URL:-}" ] || [ -z "${HIVE_TOKEN:-}" ]; then
  eval "$(HIVE_CFG="$CFG" HIVE_SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os
vals = {"HIVE_URL": None, "HIVE_TOKEN": None}
cfg = os.environ.get("HIVE_CFG")
if cfg and os.path.exists(cfg):
    c = json.load(open(cfg))
    vals["HIVE_URL"], vals["HIVE_TOKEN"] = c.get("hive_url"), c.get("hive_token")
st = os.environ.get("HIVE_SETTINGS")
if st and os.path.exists(st):
    s = json.load(open(st)).get("env", {})
    vals["HIVE_URL"] = vals["HIVE_URL"] or s.get("HIVE_URL")
    vals["HIVE_TOKEN"] = vals["HIVE_TOKEN"] or s.get("HIVE_TOKEN")
for k in ("HIVE_URL", "HIVE_TOKEN"):
    if not os.environ.get(k) and vals[k]:
        print(f'export {k}={json.dumps(vals[k])}')
PY
)"
fi

URL="${HIVE_URL:-}"; TOKEN="${HIVE_TOKEN:-}"
if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "geen HIVE_URL/HIVE_TOKEN gevonden (draai dit vanuit een project met .claude/settings.json)" >&2
  exit 1
fi
URL="${URL%/}"
auth=(-H "Authorization: Bearer $TOKEN")

cmd="${1:-}"
case "$cmd" in
  export)
    out="${2:-hivemind-backup-$(date -u +%Y%m%d-%H%M%S).json}"
    if curl -sf -m 120 "${auth[@]}" "$URL/export" -o "$out"; then
      echo "✓ back-up opgeslagen: $out ($(du -h "$out" | cut -f1))"
    else
      echo "export mislukt (org_admin-token nodig?)" >&2; exit 1
    fi
    ;;
  import)
    file="${2:-}"; mode="${3:-merge}"
    [ -f "$file" ] || { echo "geef een bestaand back-up-bestand: hive-backup.sh import <file.json> [replace]" >&2; exit 1; }
    if [ "$mode" = "replace" ]; then
      read -r -p "VERVANGEN maakt de hele hive eerst leeg en zet de back-up terug. Doorgaan? [y/N] " ok
      [ "$ok" = "y" ] || [ "$ok" = "Y" ] || { echo "afgebroken"; exit 0; }
    fi
    curl -sf -m 120 "${auth[@]}" -H "Content-Type: application/json" \
      --data-binary "@$file" "$URL/import?mode=$mode" \
      && echo || { echo "import mislukt" >&2; exit 1; }
    ;;
  *)
    echo "gebruik: hive-backup.sh export [file.json] | import <file.json> [replace]" >&2
    exit 1
    ;;
esac
