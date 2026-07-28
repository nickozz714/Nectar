#!/usr/bin/env bash
# Turn HiveMind ON for the CURRENT project. Requires a one-time global install first
# (hive-install-global.sh) — this reads the stored connection from ~/.hivemind/config.json
# and only wires this project. It never touches the SSH tunnel.
#
#   hive-enable.sh [anchors]
#
#   anchors   optional, comma-separated topic titles this project leans on,
#             e.g. "Swinkels,Fabric werkwijzen"
set -euo pipefail

ANCHORS="${1:-}"
CFG="$HOME/.hivemind/config.json"
HOOK="$HOME/.hivemind/scripts/hive_recall.sh"
PROJECT="$(pwd)"

[ -f "$CFG" ] || { echo "geen ~/.hivemind/config.json — draai eerst hive-install-global.sh" >&2; exit 1; }
[ -f "$HOOK" ] || { echo "recall-hook ontbreekt ($HOOK) — draai hive-install-global.sh opnieuw" >&2; exit 1; }

PROJECT_SLUG="$(basename "$PROJECT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/-\{2,\}/-/g; s/^-//; s/-$//')"

CFG="$CFG" ANCHORS="$ANCHORS" HOOK="$HOOK" PROJECT_SLUG="$PROJECT_SLUG" python3 - <<'PY'
import json, os

cfg = json.load(open(os.environ["CFG"]))
url, token, mcp_url = cfg["hive_url"], cfg["hive_token"], cfg["mcp_url"]
anchors = os.environ.get("ANCHORS", "")
hook = os.environ["HOOK"]
project = os.environ.get("PROJECT_SLUG", "") or "default"


def load(p):
    return json.load(open(p)) if os.path.exists(p) else {}


def save(p, d):
    with open(p, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")


# .claude/settings.json — enable + creds + project slug + the recall hook (GLOBAL script).
os.makedirs(".claude", exist_ok=True)
s = load(".claude/settings.json")
env = s.setdefault("env", {})
env.update({"HIVE_ENABLED": "1", "HIVE_URL": url, "HIVE_TOKEN": token, "HIVE_PROJECT": project})
if anchors:
    env["HIVE_ANCHORS"] = anchors
ups = s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if not any("hive_recall.sh" in json.dumps(e) for e in ups):
    ups.append({"hooks": [{"type": "command", "command": hook}]})
save(".claude/settings.json", s)

# .mcp.json — the hivemind MCP server, scoped to this project. The X-Hive-Project header
# binds the active focus (and future project-scoped tools) to this project.
m = load(".mcp.json")
m.setdefault("mcpServers", {})["hivemind"] = {
    "type": "http",
    "url": mcp_url,
    "headers": {"Authorization": "Bearer " + token, "X-Hive-Project": project},
}
save(".mcp.json", m)
print("HiveMind AAN voor project '" + project + "': .claude/settings.json (hook + env) + .mcp.json (MCP ->", mcp_url + ")")
PY

if [ -d "$PROJECT/.git" ]; then
  echo "TIP: git-repo — zet .claude/settings.json en .mcp.json in .gitignore (token niet committen)."
fi
echo "In dit project: geen lokale markdown-memories meer — gebruik hive_remember (dat is de bedoeling)."
echo "Start een NIEUWE Claude-sessie; keur de 'hivemind' MCP-server goed als erom gevraagd wordt."
