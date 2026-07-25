#!/usr/bin/env bash
# UserPromptSubmit hook: deterministic read side of HiveMind.
# Recalls relevant hive memories for the incoming prompt and emits them as context.
# The model cannot skip this — that is the point.
#
# Env: HIVE_URL, HIVE_TOKEN (required), HIVE_ANCHORS (optional, comma-separated
# topic titles the current project leans on, e.g. "Swinkels,Fabric werkwijzen").
set -uo pipefail

[ -z "${HIVE_URL:-}" ] && exit 0
[ -z "${HIVE_TOKEN:-}" ] && exit 0

INPUT=$(cat)

BODY=$(printf '%s' "$INPUT" | python3 -c '
import json, os, sys
prompt = json.load(sys.stdin).get("prompt", "").strip()
if not prompt:
    sys.exit(1)
anchors = [a.strip() for a in os.environ.get("HIVE_ANCHORS", "").split(",") if a.strip()]
print(json.dumps({"query": prompt, "anchors": anchors}))
') || exit 0

RESPONSE=$(curl -sf -m 10 -X POST "$HIVE_URL/recall" \
  -H "Authorization: Bearer $HIVE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$BODY") || exit 0

printf '%s' "$RESPONSE" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("context", ""))
'
