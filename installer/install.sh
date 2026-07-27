#!/usr/bin/env bash
# HiveMind project installer. Merges config safely — never clobbers existing keys.
# No token is baked in; you pass it here.
#
#   ./install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]
#
#   HIVE_URL       server API, e.g. http://your-server:8642  (used by the recall hook)
#   HIVE_TOKEN     account token (per person/machine)
#   anchors        optional, e.g. "Swinkels,Fabric werkwijzen"
#   ssh-user@host  REQUIRED ON macOS when HIVE_URL is a private LAN IP — see below.
#
# macOS note: the Claude Code CLI binary cannot open sockets to private LAN IPs
# (192.168/10/172.16) — a macOS "Local Network" permission bug in the CLI. curl and the
# recall hook work fine, but the MCP tools don't. Fix: this installer sets up a persistent
# localhost SSH tunnel (launchd) and points the MCP at http://localhost:<port>/mcp, which
# is loopback and not blocked. That needs passwordless SSH to the server (ssh-user@host).
set -euo pipefail

URL="${1:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]}"
TOKEN="${2:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]}"
ANCHORS="${3:-}"
SSH_TARGET="${4:-}"

KIT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(pwd)"
OS="$(uname)"

# Hook scripts under .hivemind/ so the hook has a stable path.
mkdir -p "$PROJECT/.hivemind"
cp -R "$KIT/scripts" "$PROJECT/.hivemind/"
chmod +x "$PROJECT/.hivemind/scripts/"* 2>/dev/null || true
HOOK="$PROJECT/.hivemind/scripts/hive_recall.sh"

# Derive host + port from the URL.
HOSTPORT="$(printf '%s' "$URL" | sed -E 's#^https?://##; s#/.*$##')"
SRV_HOST="${HOSTPORT%%:*}"
SRV_PORT="${HOSTPORT##*:}"
[ "$SRV_PORT" = "$SRV_HOST" ] && SRV_PORT=80

MCP_URL="${URL%/}/mcp"   # default: direct (Linux, or a public/hostname server)

is_private_ip() { printf '%s' "$1" | grep -qE '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)'; }

# ---- macOS + private LAN IP: set up a persistent localhost tunnel for the MCP ----
if [ "$OS" = "Darwin" ] && is_private_ip "$SRV_HOST"; then
  if [ -n "$SSH_TARGET" ]; then
    LOCALPORT="$SRV_PORT"
    PLIST="$HOME/Library/LaunchAgents/com.hivemind.tunnel.plist"
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
    MCP_URL="http://localhost:${LOCALPORT}/mcp"
    if curl -sf -m 5 "http://localhost:${LOCALPORT}/health" >/dev/null 2>&1; then
      echo "macOS: localhost-tunnel actief (launchd) — MCP via ${MCP_URL}"
    else
      echo "macOS: tunnel opgezet maar localhost:${LOCALPORT} reageert nog niet — check passwordless SSH naar ${SSH_TARGET}."
    fi
  else
    echo "LET OP (macOS): de Claude-binary kan geen private LAN-IP bereiken (bekende bug)."
    echo "  Geef een ssh-target mee: ./install.sh \"$URL\" \"<token>\" \"$ANCHORS\" <user@host>"
    echo "  Zonder tunnel werkt de recall-hook wel, maar de MCP-tools niet."
  fi
fi

# ---- write config (safe merge) ----
URL="$URL" TOKEN="$TOKEN" ANCHORS="$ANCHORS" HOOK="$HOOK" MCP_URL="$MCP_URL" python3 - <<'PY'
import json, os

url = os.environ["URL"].rstrip("/")
token = os.environ["TOKEN"]
anchors = os.environ.get("ANCHORS", "")
hook = os.environ["HOOK"]
mcp_url = os.environ["MCP_URL"]


def load(p):
    return json.load(open(p)) if os.path.exists(p) else {}


def save(p, d):
    with open(p, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")


# .claude/settings.json — recall hook (curl over the LAN URL; works on macOS).
os.makedirs(".claude", exist_ok=True)
s = load(".claude/settings.json")
env = s.setdefault("env", {})
env.update({"HIVE_ENABLED": "1", "HIVE_URL": url, "HIVE_TOKEN": token})
if anchors:
    env["HIVE_ANCHORS"] = anchors
ups = s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if not any("hive_recall.sh" in json.dumps(e) for e in ups):
    ups.append({"hooks": [{"type": "command", "command": hook}]})
save(".claude/settings.json", s)

# .mcp.json — MCP server (localhost on macOS via the tunnel, else the direct URL).
m = load(".mcp.json")
m.setdefault("mcpServers", {})["hivemind"] = {
    "type": "http",
    "url": mcp_url,
    "headers": {"Authorization": "Bearer " + token},
}
save(".mcp.json", m)
print("config: .claude/settings.json (hook) + .mcp.json (MCP ->", mcp_url + ")")
PY

if [ -d "$PROJECT/.git" ]; then
  echo "TIP: git-repo — zet .claude/settings.json, .mcp.json en .hivemind/ in .gitignore (token niet committen)."
fi
echo "Klaar. Start een NIEUWE Claude-sessie; keur de 'hivemind' MCP-server goed als erom gevraagd wordt."
