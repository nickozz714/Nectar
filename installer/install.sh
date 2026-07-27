#!/usr/bin/env bash
# HiveMind installer — one-liner that does the global install (once, incl. the macOS tunnel)
# and then enables the CURRENT project. Equivalent to running hive-install-global.sh once and
# hive-enable.sh per project; kept for the one-command path.
#
#   ./install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]
set -euo pipefail

URL="${1:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]}"
TOKEN="${2:?usage: install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [ssh-user@host]}"
ANCHORS="${3:-}"
SSH_TARGET="${4:-}"
KIT="$(cd "$(dirname "$0")" && pwd)"

# 1) global install (idempotent; sets up the tunnel only once)
"$KIT/hive-install-global.sh" "$URL" "$TOKEN" "$SSH_TARGET"

# 2) enable this project (uses the just-installed global scripts)
"$HOME/.hivemind/scripts/hive-enable.sh" "$ANCHORS"
