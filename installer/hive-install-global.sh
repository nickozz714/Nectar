#!/usr/bin/env bash
# HiveMind GLOBAL install — run ONCE per machine. Installs the helper scripts under
# ~/.hivemind/, stores the connection, and (on macOS behind a private LAN IP) sets up the
# localhost SSH tunnel ONCE. After this, opt a project in with `hive-enable.sh` — that never
# touches the tunnel again.
#
#   hive-install-global.sh <HIVE_URL> <HIVE_TOKEN> [ssh-user@host]
#
#   HIVE_URL       server API, e.g. http://your-server:8642
#   HIVE_TOKEN     account token (per person/machine)
#   ssh-user@host  REQUIRED ON macOS when HIVE_URL is a private LAN IP (Local Network bug):
#                  the Claude binary can't open a socket to a private IP, so the MCP goes
#                  through a persistent localhost tunnel (launchd). curl/hook work regardless.
set -euo pipefail

URL="${1:?usage: hive-install-global.sh <HIVE_URL> <HIVE_TOKEN> [ssh-user@host]}"
TOKEN="${2:?usage: hive-install-global.sh <HIVE_URL> <HIVE_TOKEN> [ssh-user@host]}"
SSH_TARGET="${3:-}"

KIT="$(cd "$(dirname "$0")" && pwd)"
HIVE_HOME="$HOME/.hivemind"
OS="$(uname)"

# --- helper scripts, once, globally ---
mkdir -p "$HIVE_HOME/scripts"
cp -f "$KIT/scripts/"* "$HIVE_HOME/scripts/"
chmod +x "$HIVE_HOME/scripts/"* 2>/dev/null || true

HOSTPORT="$(printf '%s' "$URL" | sed -E 's#^https?://##; s#/.*$##')"
SRV_HOST="${HOSTPORT%%:*}"
SRV_PORT="${HOSTPORT##*:}"
[ "$SRV_PORT" = "$SRV_HOST" ] && SRV_PORT=80
MCP_URL="${URL%/}/mcp"   # default: direct (Linux, or a public/hostname server)

is_private_ip() { printf '%s' "$1" | grep -qE '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)'; }

# --- macOS + private LAN IP: set up the localhost tunnel ONCE (idempotent) ---
if [ "$OS" = "Darwin" ] && is_private_ip "$SRV_HOST"; then
  LOCALPORT="$SRV_PORT"
  MCP_URL="http://localhost:${LOCALPORT}/mcp"
  PLIST="$HOME/Library/LaunchAgents/com.hivemind.tunnel.plist"
  if curl -sf -m 4 "http://localhost:${LOCALPORT}/health" >/dev/null 2>&1; then
    echo "tunnel: al actief op localhost:${LOCALPORT} — ongemoeid gelaten."
  elif [ -n "$SSH_TARGET" ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.hivemind.tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/ssh</string>
    <string>-N</string>
    <string>-o</string><string>ServerAliveInterval=30</string>
    <string>-o</string><string>ServerAliveCountMax=3</string>
    <string>-o</string><string>ExitOnForwardFailure=yes</string>
    <string>-o</string><string>BatchMode=yes</string>
    <string>-o</string><string>StrictHostKeyChecking=accept-new</string>
    <string>-L</string><string>${LOCALPORT}:localhost:${SRV_PORT}</string>
    <string>${SSH_TARGET}</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    sleep 3
    if curl -sf -m 5 "http://localhost:${LOCALPORT}/health" >/dev/null 2>&1; then
      echo "tunnel: opgezet (launchd) — MCP via ${MCP_URL}"
    else
      echo "tunnel: opgezet maar localhost:${LOCALPORT} reageert nog niet — check passwordless SSH naar ${SSH_TARGET}."
    fi
  else
    echo "LET OP (macOS): private LAN-IP en geen actieve tunnel. Geef een ssh-target mee:"
    echo "  hive-install-global.sh \"$URL\" \"<token>\" <user@host>"
    echo "  (Zonder tunnel werkt de recall-hook wel, maar de MCP-tools niet.)"
  fi
fi

# --- store the connection for hive-enable.sh + the helper scripts (chmod 600) ---
URL="${URL%/}" TOKEN="$TOKEN" MCP_URL="$MCP_URL" HIVE_HOME="$HIVE_HOME" python3 - <<'PY'
import json, os
cfg = {"hive_url": os.environ["URL"], "hive_token": os.environ["TOKEN"],
       "mcp_url": os.environ["MCP_URL"]}
path = os.path.join(os.environ["HIVE_HOME"], "config.json")
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
os.chmod(path, 0o600)
print("connectie opgeslagen in ~/.hivemind/config.json (chmod 600)")
PY

echo "Globaal geïnstalleerd. Zet HiveMind AAN in een project met:"
echo "  cd <project> && $HIVE_HOME/scripts/hive-enable.sh [anchors]"
