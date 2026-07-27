#!/usr/bin/env bash
# HiveMind project installer. Run from a project root (or anywhere; it writes into the
# current working directory's project). Merges config safely — never clobbers existing
# keys. No token is baked in; you pass it here.
#
#   ./install.sh <HIVE_URL> <HIVE_TOKEN> [anchors]
#
# Example:
#   ./install.sh http://your-server:8642 xxx "Swinkels,Fabric werkwijzen"
set -euo pipefail

URL="${1:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors]}"
TOKEN="${2:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors]}"
ANCHORS="${3:-}"

KIT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(pwd)"

# Place the hook scripts under .hivemind/ in the project so the hook has a stable path.
mkdir -p "$PROJECT/.hivemind"
cp -R "$KIT/scripts" "$PROJECT/.hivemind/"
chmod +x "$PROJECT/.hivemind/scripts/"* 2>/dev/null || true
HOOK="$PROJECT/.hivemind/scripts/hive_recall.sh"

URL="$URL" TOKEN="$TOKEN" ANCHORS="$ANCHORS" HOOK="$HOOK" python3 - <<'PY'
import json, os

url = os.environ["URL"].rstrip("/")
token = os.environ["TOKEN"]
anchors = os.environ.get("ANCHORS", "")
hook = os.environ["HOOK"]


def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# .claude/settings.json — merge env + the UserPromptSubmit recall hook.
os.makedirs(".claude", exist_ok=True)
settings = load(".claude/settings.json")
env = settings.setdefault("env", {})
env["HIVE_ENABLED"] = "1"
env["HIVE_URL"] = url
env["HIVE_TOKEN"] = token
if anchors:
    env["HIVE_ANCHORS"] = anchors
ups = settings.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if not any("hive_recall.sh" in json.dumps(entry) for entry in ups):
    ups.append({"hooks": [{"type": "command", "command": hook}]})
save(".claude/settings.json", settings)

# .mcp.json — register the hivemind MCP server.
mcp = load(".mcp.json")
mcp.setdefault("mcpServers", {})["hivemind"] = {
    "type": "http",
    "url": url + "/mcp",
    "headers": {"Authorization": "Bearer " + token},
}
save(".mcp.json", mcp)

print("HiveMind gekoppeld: .claude/settings.json + .mcp.json bijgewerkt.")
print("  hook ->", hook)
PY

# Reachability check.
if curl -sf -m 5 "$URL/health" >/dev/null 2>&1; then
  echo "server bereikbaar op $URL ✓"
else
  echo "LET OP: $URL/health niet bereikbaar — zit je op het juiste netwerk (LAN/VPN)?"
fi

# Nudge to keep the token out of git.
if [ -d "$PROJECT/.git" ]; then
  echo "TIP: dit is een git-repo — zet .claude/settings.json, .mcp.json en .hivemind/ in .gitignore om het token niet te committen."
fi

echo "Klaar. Start een NIEUWE Claude-sessie in dit project; de recall-hook draait dan mee."
