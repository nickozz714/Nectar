# Nectar plugin for Claude Code

One package that turns any Claude Code CLI into a bee:

- **`.mcp.json`** — connects the `hivemind` MCP server (`${HIVE_URL}/mcp`, bearer `${HIVE_TOKEN}`).
- **`hooks/hooks.json`** — `UserPromptSubmit` hook: every prompt is enriched with
  relevant hive memories (deterministic; the model cannot skip it). Set `HIVE_ANCHORS`
  per project to get that project's slice of the mind first.
- **`skills/hive-memory`** — teaches the model how to write good memories, promote
  knowledge across contexts and pick up governance chores.
- **`scripts/hive-secret`** — env-injection for vault secrets:
  `export MY_KEY=$(hive-secret MY_KEY)`.
- **`scripts/hive-init`** — anchor a project directory to hive topics:
  `cd ~/projects/swinkels && hive-init "Swinkels,Fabric werkwijzen"` writes
  `HIVE_ANCHORS` into the project's `.claude/settings.json` (every session in that
  directory inherits it) and suggests a CLAUDE.md block. Anchors boost the project's
  slice of the mind in recall ranking without hiding the rest.

## Setup

```bash
export HIVE_URL=https://hive.example.com
export HIVE_TOKEN=<account token>
export HIVE_ANCHORS="Swinkels,Fabric werkwijzen"   # optional, per project
chmod +x scripts/*.sh scripts/hive-secret
```

Then install the plugin directory in Claude Code (marketplace entry or local plugin).
