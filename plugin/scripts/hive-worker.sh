#!/usr/bin/env bash
# hive-worker.sh — headless swarm worker: drains the Nectar Pollen queue once, including
# cognition (world-research) Pollen. Meant to be scheduled via cron/launchd (see
# installer/com.hivemind.worker.plist.example), but running it by hand is fine too.
#
# Usage: hive-worker.sh [project-dir]
#   project-dir: a hive-ENABLED project (recall hook + .mcp.json wired by hive-enable.sh);
#                defaults to $HIVE_WORKER_PROJECT, then the current directory.
#
# The worker is just one more swarm member: it follows the shared "pollinate-nectar"
# skill from the hive's skill library, so updating that skill updates every worker.
set -euo pipefail

DIR="${1:-${HIVE_WORKER_PROJECT:-$PWD}}"
cd "$DIR"
if [ ! -f .mcp.json ]; then
  echo "hive-worker: $DIR is not hive-enabled (.mcp.json missing) — run hive-enable.sh there first" >&2
  exit 1
fi
command -v claude >/dev/null || { echo "hive-worker: claude CLI not on PATH" >&2; exit 1; }

LOGDIR="$HOME/.hivemind/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/worker-$(date +%Y%m%d).log"

PROMPT='Je bent een Nectar swarm-worker (headless, geen mens aanwezig). Werk de open
Pollen-wachtrij af volgens de gedeelde skill "pollinate-nectar" — haal die op via
skill_list → skill_get als je hem niet lokaal hebt. Cognition-Pollen doe je volledig:
claim, entiteiten uit de bron-memory halen, per entiteit eerst hive_search, websearch
voor het onbekende, compacte glossary-memories met tag world-knowledge en bron-URLs,
hive_relate de verbanden, afsluiten met hive_resolve_cognition (vervolgvragen alleen
via follow_up). Kun je een Pollen niet beoordelen of mis je webtoegang: hive_release
en laat hem staan. Rapporteer aan het eind kort wat je deed.'

{
  echo "=== hive-worker $(date -u +%FT%TZ) in $DIR"
  claude -p "$PROMPT" --allowedTools "mcp__hivemind__*,WebSearch,WebFetch" 2>&1
  echo "=== done $(date -u +%FT%TZ)"
} >>"$LOG"
