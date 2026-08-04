# Nectar — install & enable (instructions for Claude)

You've been given this install kit (`hivemind-install.zip`). The model is **install once
globally per machine**, then **enable per project where relevant**. In an enabled
project, org memories are fetched automatically on every prompt (the recall hook) and
you work with the MCP tools (`hive_search`, `hive_remember`, …).

**This kit contains NO token.** Ask the user for the details below.

## What you need from the user
- **HIVE_URL** — e.g. `http://your-server:8642` (the server API on the LAN).
- **HIVE_TOKEN** — the account token (per person/machine; individually revocable).
- **anchors** (optional, per project) — comma list of topics this project leans on.
- **On macOS with a LAN IP: an SSH target** `user@host` (e.g. `user@your-server`) — for
  the one-time tunnel. See the macOS explanation below.

## ⚠️ Important on macOS (read this)
On macOS the Claude Code CLI binary **cannot open a socket to a private LAN IP**
(192.168.x / 10.x / 172.16.x) — a known bug (issues #27828 / #55169). That's why the MCP runs
via a **localhost tunnel** (`launchd`, `localhost:<port>` → server). That tunnel is
**global and set up once** by the global install — enabling projects never touches
it again. Required: **passwordless SSH to the server**:
```bash
ssh-copy-id user@host    # one-time, if 'ssh user@host' still asks for a password
```
On **Linux** this doesn't apply: the MCP talks directly to the LAN IP (no tunnel).

## Step 1 — install globally (once per machine)
```bash
unzip -o hivemind-install.zip
cd hivemind-install
# macOS (with a LAN IP): supply the ssh target
./hive-install-global.sh "<HIVE_URL>" "<HIVE_TOKEN>" "user@host"
# Linux / public server: the ssh target may be omitted
./hive-install-global.sh "<HIVE_URL>" "<HIVE_TOKEN>"
```
This places the helper scripts in `~/.hivemind/scripts/`, stores the connection in
`~/.hivemind/config.json` (chmod 600), and on macOS+LAN-IP sets up the tunnel (idempotent —
run it again and an active tunnel is left untouched).

## Step 2 — enable per project (where relevant)
```bash
cd <project>
~/.hivemind/scripts/hive-enable.sh "<anchors>"     # anchors optional
```
This merges into this project: `.claude/settings.json` (recall hook + `HIVE_ENABLED=1` + creds)
and `.mcp.json` (the `hivemind` MCP server, only here). No tunnel fuss. Then start a
**new** Claude session and approve the `hivemind` MCP server.

> One-command variant (does step 1 idempotently + step 2 for the current project):
> `./install.sh "<HIVE_URL>" "<HIVE_TOKEN>" "<anchors>" "user@host"`

## Verifying
- `claude mcp list` → `hivemind ... ✔` (on macOS only after the tunnel + localhost URL).
- Or ask a project-specific question that can only be answered from Nectar.

## Important
- **Don't commit the token.** In a git repo: `.claude/settings.json` and `.mcp.json` in
  `.gitignore` (or `settings.local.json`).
- **In an enabled project: no local markdown memories.** Write memories into Nectar
  via `hive_remember` (type `decision` for choices), skills via `skill_put`.
- **Updating** goes via the MCP tool `hive_update` (or `~/.hivemind/scripts/hive-update.sh`) —
  which refreshes the global scripts; you don't need to reinstall.
- No token? Ask an org_admin: `hive_invite` (invite code) or `/manage/tokens`.
