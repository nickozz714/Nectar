#!/usr/bin/env bash
# Install a shared skill from HiveMind into this project's .claude/skills/ over plain HTTP.
# Works without the MCP connection (same transport as the recall hook).
#
#   hive-skill-install.sh --list                 list available skills
#   hive-skill-install.sh <skill name or uid>    fetch it and write .claude/skills/<slug>/
#
# HIVE_URL/HIVE_TOKEN are read from the project's .claude/settings.json (written by the
# installer); env vars of the same name override.
set -uo pipefail

PROJECT="$(pwd)"
SETTINGS="$PROJECT/.claude/settings.json"
CFG="$HOME/.hivemind/config.json"

# creds: env → ~/.hivemind/config.json → this project's .claude/settings.json
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

if [ "${1:-}" = "--list" ] || [ -z "${1:-}" ]; then
  echo "Beschikbare skills in de hive:"
  curl -sf -m 15 "${auth[@]}" "$URL/skills" | python3 -c '
import json, sys
skills = json.load(sys.stdin)
if not skills:
    print("  (nog geen skills)")
for s in skills:
    print(f"  - {s[\"title\"]}   [{s[\"uid\"]}]")
' || { echo "kon skills niet ophalen" >&2; exit 1; }
  [ -z "${1:-}" ] && echo && echo "Installeren: hive-skill-install.sh \"<naam of uid>\""
  exit 0
fi

WANT="$1"

# Resolve a name to a uid (exact uid passes through). Case-insensitive title match.
UID_RESOLVED="$(WANT="$WANT" curl -sf -m 15 "${auth[@]}" "$URL/skills" | WANT="$WANT" python3 -c '
import json, os, sys
want = os.environ["WANT"].strip()
skills = json.load(sys.stdin)
byuid = {s["uid"]: s for s in skills}
if want in byuid:
    print(want); sys.exit(0)
hits = [s for s in skills if s["title"].strip().lower() == want.lower()]
if not hits:
    hits = [s for s in skills if want.lower() in s["title"].strip().lower()]
if len(hits) == 1:
    print(hits[0]["uid"])
elif not hits:
    sys.stderr.write(f"geen skill gevonden voor: {want}\n"); sys.exit(2)
else:
    sys.stderr.write("meerdere skills matchen; kies via uid:\n" +
                     "".join(f"  - {h[\"title\"]}   [{h[\"uid\"]}]\n" for h in hits)); sys.exit(3)
')" || exit 1

# Fetch the skill + files and write them under .claude/skills/<slug>/.
curl -sf -m 20 "${auth[@]}" "$URL/skills/$UID_RESOLVED" | PROJECT="$PROJECT" python3 -c '
import json, os, re, sys
skill = json.load(sys.stdin)
title = (skill.get("title") or "skill").strip()
slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "skill"
root = os.path.join(os.environ["PROJECT"], ".claude", "skills", slug)
files = skill.get("files") or []
if not files:
    sys.stderr.write("skill heeft geen bestanden\n"); sys.exit(1)
written = []
for f in files:
    # Guard against path traversal from the stored path.
    rel = os.path.normpath(f["path"]).lstrip("/")
    if rel.startswith(".."):
        continue
    dest = os.path.join(root, rel)
    os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
    with open(dest, "w") as out:
        out.write(f.get("content") or "")
    written.append(rel)
print(f"Skill \"{title}\" geïnstalleerd in .claude/skills/{slug}/")
for w in written:
    print(f"  - {w}")
print("Start een nieuwe Claude-sessie (of herlaad) zodat de skill wordt opgepikt.")
' || { echo "installeren mislukt" >&2; exit 1; }
