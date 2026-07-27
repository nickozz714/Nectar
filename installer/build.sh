#!/usr/bin/env bash
# Build the maintained install package: hivemind-install.zip at the repo root.
# Source of truth for the hook scripts is plugin/scripts/ — this assembles them together
# with INSTRUCTIONS.md and install.sh. RE-RUN THIS whenever plugin/scripts, install.sh or
# INSTRUCTIONS.md change, and commit the updated zip.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
PKG="$STAGE/hivemind-install"

mkdir -p "$PKG/scripts"
cp "$REPO/installer/INSTRUCTIONS.md" "$PKG/INSTRUCTIONS.md"
cp "$REPO/installer/install.sh" "$PKG/install.sh"
cp "$REPO/plugin/scripts/hive_recall.sh" "$PKG/scripts/hive_recall.sh"
cp "$REPO/plugin/scripts/hive-secret" "$PKG/scripts/hive-secret"
cp "$REPO/plugin/scripts/hive-skill-install.sh" "$PKG/scripts/hive-skill-install.sh"
cp "$REPO/plugin/scripts/hive-update.sh" "$PKG/scripts/hive-update.sh"
chmod +x "$PKG/install.sh" "$PKG/scripts/"*

( cd "$STAGE" && zip -qr hivemind-install.zip hivemind-install )
mv -f "$STAGE/hivemind-install.zip" "$REPO/hivemind-install.zip"
rm -rf "$STAGE"

echo "built $REPO/hivemind-install.zip"
unzip -l "$REPO/hivemind-install.zip"
