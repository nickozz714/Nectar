# HiveMind 🐝

The shared mind of an organization. Claude models are the **bees**; HiveMind is the
**hive** they collectively maintain — one shared, scoped, self-curating memory with
skills and an account-bound secrets vault, exposed over MCP.

See [DESIGN.md](DESIGN.md) for the full design.

## Quick start

```bash
cp .env.example .env
# edit .env: set ADMIN_TOKEN, SECRET_MASTER_KEY (see below), optionally embeddings
docker compose up -d --build
```

Generate a vault master key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Bootstrap an org + account + token

```bash
H="Authorization: Bearer $ADMIN_TOKEN"
API=http://localhost:8642

ORG=$(curl -s -X POST $API/admin/orgs -H "$H" -H 'Content-Type: application/json' -d '{"name": "MyCompany"}' | jq -r .uid)
TEAM=$(curl -s -X POST $API/admin/teams -H "$H" -H 'Content-Type: application/json' -d "{\"org_uid\": \"$ORG\", \"name\": \"Data\"}" | jq -r .uid)
ACC=$(curl -s -X POST $API/admin/accounts -H "$H" -H 'Content-Type: application/json' -d "{\"org_uid\": \"$ORG\", \"team_uid\": \"$TEAM\", \"name\": \"nick\"}" | jq -r .uid)
curl -s -X POST $API/admin/tokens -H "$H" -H 'Content-Type: application/json' -d "{\"account_uid\": \"$ACC\", \"label\": \"laptop\"}"
# → { "token": "..." }  (shown once — store it)
```

### Connect a Claude Code client

Install the plugin in `plugin/` (or add it as a marketplace entry), then set in your env:

```bash
export HIVE_URL=http://localhost:8642
export HIVE_TOKEN=<account token>
export HIVE_ANCHORS="Swinkels,Fabric werkwijzen"   # optional, per project
```

The plugin gives you:
- **`UserPromptSubmit` hook** — every prompt is answered with relevant hive memories
  injected as context (anchored to your project's topics first).
- **MCP tools** — `hive_search`, `hive_get`, `hive_remember`, `hive_relate`,
  `hive_suggest`, `hive_chores`, `hive_resolve_chore`, `skill_list`, `skill_get`, `topic_list`.
- **`hive-secret` script** — `export X=$(plugin/scripts/hive-secret NAME)`; secrets go
  into env, never into chat context.
- **Skill** — teaches the model how to write good memories, relate/promote knowledge and
  pick up governance chores.

### Looking at the mind

Neo4j Browser runs at http://localhost:7474 (user `neo4j`, password from `.env`) — a
literal window into the hive.

## Development

```bash
cd server
pip install -r requirements.txt
uvicorn src.main:app --reload  # needs a running Neo4j (docker compose up neo4j)
```
