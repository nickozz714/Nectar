# HiveMind — Installation & first use

From zero to a working, connected hive. Assumes Docker and a recent Claude Code CLI.

---

## 1. Run the hive (one container)

```bash
git clone https://github.com/nickozz714/HiveMind.git
cd HiveMind
cp .env.example .env
```

Edit `.env` and set three values:

```ini
ADMIN_TOKEN=<paste: openssl rand -hex 24>
NEO4J_PASSWORD=<paste: openssl rand -hex 12>
SECRET_MASTER_KEY=<paste the output of the command below>
```

Generate the vault key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Start it (first build downloads the embedding model into the image; a few minutes once):

```bash
docker compose up -d --build
curl -s localhost:8642/health   # -> {"status":"ok"}
```

Everything is now running in one container: the API + MCP on **8642**, the Neo4j Browser on
**7474**, and local embeddings in-process. Nothing talks to the cloud.

## 2. Create an org, an account and a token

An account belongs to a **person** and has a **role**: `member` (read/write/suggest) →
`maintainer` (also resolves swarm chores) → `org_admin` (also reviews scope-widening).

```bash
export ADMIN=<your ADMIN_TOKEN>
API=http://localhost:8642
H="Authorization: Bearer $ADMIN"; CT="Content-Type: application/json"

ORG=$(curl -s -X POST $API/admin/orgs -H "$H" -H "$CT" \
  -d '{"name":"MyCompany"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["uid"])')

ACC=$(curl -s -X POST $API/admin/accounts -H "$H" -H "$CT" \
  -d "{\"org_uid\":\"$ORG\",\"name\":\"nick\",\"person\":\"The Nectar authors\",\"role\":\"org_admin\"}" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["uid"])')

curl -s -X POST $API/admin/tokens -H "$H" -H "$CT" \
  -d "{\"account_uid\":\"$ACC\",\"label\":\"laptop\"}"
# -> {"token":"..."}   <-- shown ONCE; store it as your HIVE_TOKEN
```

Teams are optional (`POST /admin/teams` then pass `team_uid` when creating accounts) and
give you team-scoped knowledge; a single org works fine to start.

You can also do all of this in the **GUI** — open `http://localhost:8642/ui`, log in with a
token, and use the **Beheer** tab (it asks for the admin token) to add accounts and mint,
rotate or clean up tokens.

## 3. Connect a project (opt-in, per directory)

HiveMind does **nothing** until a project opts in — so other projects and ad-hoc Claude
sessions stay hive-free.

Install the plugin (`plugin/`) in Claude Code, set the connection, then anchor the project:

```bash
export HIVE_URL=http://localhost:8642
export HIVE_TOKEN=<the account token from step 2>

cd ~/projects/mycompany-dataplatform
/path/to/HiveMind/plugin/scripts/hive-init "Data Modelling,MyCompany"
```

`hive-init` writes `HIVE_ENABLED`, your anchor topics, and (optionally, as a 2nd argument) a
project-specific token into this project's `.claude/settings.json`. Every Claude Code
session started in this directory now:

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
