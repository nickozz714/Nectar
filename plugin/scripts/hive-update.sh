#!/usr/bin/env bash
# Refresh this project's HiveMind client files (recall hook + helper scripts) to the
# latest maintained version, by re-fetching the server's install package over HTTP.
# Your token and settings are left untouched — only .hivemind/scripts/ is refreshed.
#
#   hive-update.sh            update the scripts in the current project
#
# HIVE_URL/HIVE_TOKEN are read from .claude/settings.json (env vars override).
#
# Note: this updates only the LOCAL scripts. The "how to work with HiveMind" instructions
# and the shared skills live server-side and reach you automatically — the instructions via
# the recall hook (system memory, injected every prompt), the tools via the MCP server on
# reconnect. So most of the time you don't need this at all; run it when the hook or the
# helper scripts themselves changed.
set -uo pipefail

PROJECT="$(pwd)"
SETTINGS="$PROJECT/.claude/settings.json"
[ -f "$SETTINGS" ] || { echo "geen .claude/settings.json — draai dit vanuit een hive-project" >&2; exit 1; }

eval "$(HIVE_SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os
s = json.load(open(os.environ["HIVE_SETTINGS"])).get("env", {})
for k in ("HIVE_URL", "HIVE_TOKEN"):
    if not os.environ.get(k) and s.get(k):
        print(f'export {k}={json.dumps(s[k])}')
PY
)"

URL="${HIVE_URL:-}"; TOKEN="${HIVE_TOKEN:-}"
[ -z "$URL" ] || [ -z "$TOKEN" ] && { echo "geen HIVE_URL/HIVE_TOKEN in settings.json" >&2; exit 1; }
URL="${URL%/}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "install-pakket ophalen van $URL/install.zip …"
if ! curl -sf -m 30 -H "Authorization: Bearer $TOKEN" "$URL/install.zip" -o "$TMP/kit.zip"; then
  echo "kon install.zip niet ophalen (token geldig? server bereikbaar?)" >&2
  exit 1
fi

unzip -qo "$TMP/kit.zip" -d "$TMP" || { echo "uitpakken mislukt" >&2; exit 1; }
SRC="$(dirname "$(find "$TMP" -name hive_recall.sh -print -quit)")"
[ -d "$SRC" ] || { echo "geen scripts in het pakket gevonden" >&2; exit 1; }

mkdir -p "$PROJECT/.hivemind/scripts"
cp -f "$SRC"/* "$PROJECT/.hivemind/scripts/"
chmod +x "$PROJECT/.hivemind/scripts/"* 2>/dev/null || true

echo "bijgewerkt: .hivemind/scripts/"
ls -1 "$PROJECT/.hivemind/scripts/" | sed 's/^/  - /'
echo "Klaar. De recall-hook gebruikt de nieuwe versie bij je volgende prompt."
