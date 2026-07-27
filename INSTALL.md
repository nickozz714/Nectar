# HiveMind — Installation & first use

From zero to a working, connected hive. Assumes Docker and a recent Claude Code CLI.

---

## 1. Run the hive (one container, zero config)

```bash
git clone https://github.com/nickozz714/HiveMind.git
cd HiveMind
docker compose up -d --build           # first build bakes in the embedding model (a few min)
curl -s localhost:8642/health          # -> {"status":"ok"}
```

That's it — no `.env` needed to start. Everything runs in one container: API + MCP on
**8642**, the Neo4j Browser on **7474**, local embeddings in-process. Nothing talks to the
cloud. (Optional hardening — Neo4j password, vault key, a super-admin token — is in
`.env.example`; the vault key auto-generates and persists on the data volume.)

## 2. Register — the first user becomes admin, no token needed

Registration is self-service. The **very first** person to register creates the org and
becomes `org_admin`; **everyone after** needs an invite code from an org_admin. A role
(`member` → `maintainer` → `org_admin`) is bound to the returned token, so from then on a
client needs **only that token**.

The easiest path is to let `hive-init` do it (step 3). By hand it's one call:

```bash
API=http://localhost:8642

# first user of a fresh hive -> org_admin, no invite:
curl -s -X POST $API/register -H "Content-Type: application/json" \
  -d '{"name":"The Nectar authors","email":"you@example.com"}'
# -> {"token":"...","role":"org_admin", ...}   <-- store the token
```

To add colleagues later, an org_admin mints an invite **with their own token** (no admin
token involved):

```bash
curl -s -X POST $API/manage/invites -H "Authorization: Bearer $ORG_ADMIN_TOKEN" \
  -H "Content-Type: application/json" -d '{"role":"member","uses":1}'
# -> {"code":"..."}   share this; the colleague registers with "invite_code":"..."
```

Roles are managed the same way (`POST /manage/tokens/{hash}/role`), and everything above is
also in the GUI **Beheer** tab. Teams are optional (`/admin/teams`, needs the operator
`ADMIN_TOKEN`) for team-scoped knowledge; a single org is fine to start.

## 3. Connect a project (opt-in, per directory)

HiveMind does **nothing** until a project opts in — so other projects and ad-hoc Claude
sessions stay hive-free.

**Easiest: the self-install kit** (`hivemind-install.zip` from the repo root). Drop it in
a project and let Claude install it — it handles the macOS tunnel automatically:

```bash
unzip -o hivemind-install.zip && cd hivemind-install
# macOS + LAN IP: pass the SSH target (4th arg) so it sets up the localhost tunnel:
./install.sh "http://your-server:8642" "<token>" "Data Modelling,MyCompany" "user@your-server"
# Linux / hostname server: drop the SSH target.
```

> **macOS:** the Claude Code CLI can't reach a private LAN IP (Local Network permission bug,
> claude-code #27828/#55169) — `claude mcp list` shows `FailedToOpenSocket`. The installer
> routes the MCP through a persistent `launchd` localhost SSH tunnel and points it at
> `http://localhost:<port>/mcp`; the recall hook keeps using the LAN IP (curl works). Needs
> passwordless SSH to the server (`ssh-copy-id user@host`). Not needed on Linux.

**Alternatively, the plugin + `hive-init`:** install the plugin (`plugin/`) in Claude Code,
then from the project directory either register on the spot or pass an existing token:

```bash
export HIVE_URL=http://localhost:8642
cd ~/projects/mycompany-dataplatform

# register a user and store the token in one go (first user needs no invite):
/path/to/HiveMind/plugin/scripts/hive-init "Data Modelling,MyCompany" \
    --register "The Nectar authors" you@example.com [invite-code-if-not-first]

# ...or, if you already have a token:
#   HIVE_TOKEN=<token> /path/to/HiveMind/plugin/scripts/hive-init "Data Modelling,MyCompany"
```

`hive-init` writes `HIVE_ENABLED`, your anchor topics and the token into this project's
`.claude/settings.json`. Every Claude Code session started in this directory now:

- gets relevant hive memories injected on **every prompt** (ranked toward your anchor
  topics — a preference, not a filter), via a deterministic hook;
- can call the MCP tools: `hive_search`, `hive_get`, `hive_remember`, `hive_relate`,
  `hive_suggest`, `hive_chores`, `skill_put`, `workflow_put`, `skill_list/get`,
  `topic_list`, `hive_resolve_chore`;
- can fetch secrets into env without leaking them into chat:
  `export MY_KEY=$(/path/to/HiveMind/plugin/scripts/hive-secret MY_KEY)`.

That's it — start Claude in that directory and the hive is live.

## 4. Look at your mind

- **GUI** `http://localhost:8642/ui` — interactive graph (click a node for detail + lineage,
  double-click to expand), search, the **Chores**, **Governance** and (org_admins)
  **Review** tabs.
- **Neo4j Browser** `http://localhost:7474` — user `neo4j`, password from `.env`.

---

## Remote access

To reach the hive when you're not on the home network, run the bundled VPN container
on the machine that hosts the hive:

```bash
cd deploy/VPN
docker compose up -d
docker exec VPN /app/show-peer a-device   # QR / config for a device
```

Then forward **UDP 51820** on your router to that machine. VPN is silent to anyone
without a key. Full notes (per-device enrolment, split tunnel, revoking a device) in
[`deploy/VPN/README.md`](deploy/VPN/README.md). Once connected, point `HIVE_URL`
at the hive's LAN address.

## Operations

- **Backup:** `./scripts/backup.sh` → `backups/hive-data-<stamp>.tgz` (stops briefly for a
  consistent copy). Restore instructions are in the script header.
- **Rotate a token:** `POST /admin/tokens/<hash>/rotate` (or the Beheer tab).
- **Clean up expired/revoked tokens:** `POST /admin/tokens/cleanup?org_uid=<org>`.
- **Re-embed after a model change:** `POST /admin/reembed?org_uid=<org>`.
- **Change the embedding model:** rebuild with
  `docker compose build --build-arg EMBEDDINGS_MODEL=<fastembed-model>` and set
  `EMBEDDINGS_DIM` in `docker-compose.yml` to match, then run the re-embed above.

## Troubleshooting

- **`/health` not responding after `up`:** the first boot builds the image and Neo4j takes
  ~20–30s; `docker compose logs -f` shows progress. `init_db` retries the DB connection.
- **UI loads but shows nothing:** you're logged in with a token that has no visible
  knowledge yet — write something with `hive_remember` or check the token's scope.
- **"No declared setting with name: URI":** you passed Neo4j client env vars to the Neo4j
  process; the bundled `start.sh` already strips these — only relevant if you customized it.
- **Tests wiped data:** the test suite is destructive by design; always give it its own
  Neo4j on a separate port (see README), never the hive's.
