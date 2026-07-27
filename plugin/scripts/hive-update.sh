#!/usr/bin/env bash
# Refresh the GLOBAL HiveMind helper scripts (~/.hivemind/scripts/) to the latest maintained
# version by re-fetching the server's install package over HTTP. Your connection/token are
# left untouched. This is the shell fallback for the `hive_update` MCP tool.
#
#   hive-update.sh
#
# Connection is read from ~/.hivemind/config.json (env HIVE_URL/HIVE_TOKEN override).
set -uo pipefail

HIVE_HOME="$HOME/.hivemind"
CFG="$HIVE_HOME/config.json"

# creds: env → ~/.hivemind/config.json
if [ -z "${HIVE_URL:-}" ] || [ -z "${HIVE_TOKEN:-}" ]; then
  if [ -f "$CFG" ]; then
    eval "$(HIVE_CFG="$CFG" python3 - <<'PY'
import json, os
c = json.load(open(os.environ["HIVE_CFG"]))
for k, v in (("HIVE_URL", c.get("hive_url")), ("HIVE_TOKEN", c.get("hive_token"))):
    if not os.environ.get(k) and v:
        print(f'export {k}={json.dumps(v)}')
PY
)"
  fi
fi

URL="${HIVE_URL:-}"; TOKEN="${HIVE_TOKEN:-}"
[ -z "$URL" ] || [ -z "$TOKEN" ] && { echo "geen HIVE_URL/HIVE_TOKEN (draai hive-install-global.sh)" >&2; exit 1; }
URL="${URL%/}"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "install-pakket ophalen van $URL/install.zip …"
curl -sf -m 30 -H "Authorization: Bearer $TOKEN" "$URL/install.zip" -o "$TMP/kit.zip" \
  || { echo "kon install.zip niet ophalen (token geldig? server bereikbaar?)" >&2; exit 1; }
unzip -qo "$TMP/kit.zip" -d "$TMP" || { echo "uitpakken mislukt" >&2; exit 1; }
SRC="$(dirname "$(find "$TMP" -name hive_recall.sh -print -quit)")"
[ -d "$SRC" ] || { echo "geen scripts in het pakket" >&2; exit 1; }

mkdir -p "$HIVE_HOME/scripts"
cp -f "$SRC"/* "$HIVE_HOME/scripts/"
chmod +x "$HIVE_HOME/scripts/"* 2>/dev/null || true
echo "bijgewerkt: ~/.hivemind/scripts/"
ls -1 "$HIVE_HOME/scripts/" | sed 's/^/  - /'
echo "Klaar. Alle hive-projecten gebruiken meteen de nieuwe scripts."
