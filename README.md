# Nectar 🐝

**The shared mind of an organization.** Claude models are the **bees**; Nectar is the
**hive** they collectively maintain — one shared, scoped, self-curating memory with skills,
workflows and an account-bound secrets vault, exposed over MCP. Every Claude Code CLI logs
in with an account token and gets the org's knowledge, ranked toward whatever project it is
working on, injected automatically on every prompt.

It runs **fully offline in one container** (Neo4j + API + local embeddings) — no cloud, no
data leaving your network.

- **New here? → [INSTALL.md](INSTALL.md)** gets you from zero to a working hive in ~5 minutes.
- **How it works & why → [DESIGN.md](DESIGN.md)**
- **What's next → [TODO.md](TODO.md)**

---

## What you get

| | |
|---|---|
| 🧠 **Graph memory** | Topics at the top (subjects, projects, systems), knowledge linked underneath as a multi-parent graph. Retrieval traverses the graph *and* ranks semantically. |
| ⏳ **Recency decay** | Memories age when unused and rejuvenate when read — the current, relevant set surfaces first, so recall is fast and cheap. Decisions & conventions decay slowly. |
| ✍️ **Guarded writes** | A deterministic write-gate: quality checks, PII block, two-band dedup, automatic topic reuse, sensitivity classification. |
| 🐝 **Swarm governance** | Nobody edits a memory casually — mutations need consensus from multiple models; the swarm resolves the queue in passing. Scope-widening is the one thing a human decides. |
| 🔐 **Secrets vault** | Per-account, encrypted, grant-based, audited — fetched into env vars, never into chat context. |
| 🛡️ **Governance & lineage** | Purview-style dashboard: classification, provenance (person → account → model), full audit trail, per-node lineage. |
| 🖥️ **Web GUI** | Click through the mind, search, handle chores, review, manage accounts — at `/ui`. |
| 🔌 **One plugin** | Per-project opt-in for any Claude Code CLI: recall hook + skill + secret helper. |

## Quick start

```bash
cp .env.example .env          # then set ADMIN_TOKEN, NEO4J_PASSWORD, SECRET_MASTER_KEY
docker compose up -d --build  # Neo4j + API + embeddings, one container
```

Bootstrap an org and a token, connect a project, done — the full walkthrough is in
**[INSTALL.md](INSTALL.md)**. The GUI is then at `http://localhost:8642/ui`, the Neo4j
Browser (a literal window into the mind) at `http://localhost:7474`.

## Connect a project (self-install kit)

The maintained package **`hivemind-install.zip`** (repo root) lets Claude wire things up
itself. The model is **install once globally, then enable per project**:

- **Global (once per machine)** — `hive-install-global.sh <HIVE_URL> <HIVE_TOKEN> [user@host]`
  puts the helper scripts in `~/.hivemind/scripts/`, stores the connection in
  `~/.hivemind/config.json`, and (on macOS + a LAN IP) sets up the localhost SSH tunnel
  **once**.
- **Per project (where relevant)** — `~/.hivemind/scripts/hive-enable.sh [anchors]` wires
  that project's `.claude/settings.json` (recall hook + `HIVE_ENABLED`) and `.mcp.json`
  (the `hivemind` MCP server, scoped to that project). It never touches the tunnel again.
  In an enabled project you write memories to the hive (`hive_remember`), not local markdown.

`install.sh <HIVE_URL> <HIVE_TOKEN> [anchors] [user@host]` is a one-command wrapper (global
+ enable current project). **No token is baked into the zip**; it's supplied at install time
(per person/machine, mint one with `hive_invite` or `/manage/tokens`).

**macOS caveat (handled by the installer):** the Claude Code CLI binary can't open a socket
to a private LAN IP (192.168/10/172.16) — a known macOS "Local Network" permission bug in
the CLI (claude-code #27828/#55169), so `claude mcp list` reports `FailedToOpenSocket` even
though curl and the recall hook work. Fix: the MCP goes through a **localhost SSH tunnel**.
On macOS + a LAN IP, pass the SSH target (`user@host`); the installer sets up a persistent
`launchd` tunnel (`localhost:<port>` → server) and points the MCP at `http://localhost:<port>/mcp`.
The recall hook keeps using the LAN IP (curl works). Needs passwordless SSH to the server
(`ssh-copy-id user@host`). Linux and hostname/public servers connect directly, no tunnel.

Maintenance: the zip is assembled from `installer/` + `plugin/scripts/` by
`installer/build.sh`. Re-run it and commit the zip whenever those change.

## Deploy & login

How people sign in is a **deploy-time choice, not baked into the image**: the wizard,
password and token logins always work, and Microsoft Entra SSO switches on only if you pass
its config at rollout (leave it out for an org that doesn't want it). The full rollout &
auth-configuration guide is **[deploy/README.md](deploy/README.md)** (with
[deploy/entra/README.md](deploy/entra/README.md) for the Entra app-registration and
[deploy/azure/README.md](deploy/azure/README.md) for Azure Container Apps).

## Remote access

`deploy/VPN/` is a hardened VPN container so you can reach the hive from
anywhere on your own encrypted network — see [INSTALL.md](INSTALL.md#remote-access).

## Tests

```bash
cd server
pip install -r requirements.txt pytest
NEO4J_URI=bolt://localhost:7688 NEO4J_PASSWORD=test python -m pytest
```

Tests need their **own throwaway Neo4j** (they wipe the database each run — never point them
at a populated hive):

```bash
docker run -d --name hive-test -p 7688:7687 -e NEO4J_AUTH=neo4j/test neo4j:5-community
```

CI runs the same suite on every push (`.github/workflows/ci.yml`).

## Backups

```bash
./scripts/backup.sh   # stops briefly, tars the data volume, restarts -> backups/*.tgz
```

Your data lives on the `hive-data` Docker volume and survives restarts and rebuilds; only
`docker compose down -v` erases it.
