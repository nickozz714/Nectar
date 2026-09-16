# Nectar — automated setup runbook

This page is written to be **executed by an AI agent** — Claude Code or anything comparable
with shell access on the target machine. Every step carries a check; nothing is left to
judgement except the two inputs listed below. A human can follow it top to bottom just as
well.

`INSTALL.md` is the narrative version for a person who wants to understand what they are
doing. This one is the deterministic version for something that just has to get it right.

> **How to work through this, agent.** Run the steps in order. Every step has a check;
> **if a check does not hold, stop and report what happened** — do not continue and do not
> improvise an alternative. All steps are idempotent: running them twice is safe.

## What you are installing, and where

**One machine runs the hive; everyone else connects to it.** This is the opposite of a
per-person install: Nectar *is* the shared memory, so a second instance means a second,
disconnected brain. Install it once, then connect each person's Claude Code to it with
their own token.

| | |
| --- | --- |
| **Shape** | One stateful container: Neo4j + the API + the local models, all in-process |
| **Runs where** | A machine that stays on — a server, a NAS, a spare box. Not a laptop that sleeps |
| **Clients** | Claude Code (or any MCP client) per project directory, each with its own account token and role |
| **Network** | Nothing leaves your network. Embeddings and reranking are local models baked into the image |

> **Exactly one replica, one volume.** Nectar is single-writer: Neo4j Community is embedded
> and owns the store. Never point two instances at the same volume, and never scale out —
> scale *up* (CPU/RAM). There is no clustering here to fall back on.

## 0. Inputs you need

| Name | What it is | Where it comes from |
| --- | --- | --- |
| `ADMIN_NAME` / `ADMIN_EMAIL` | the first person to register, who becomes `org_admin` | the user tells you, or you ask once |
| `NECTAR_HOST` | hostname or LAN IP of this machine | only needed when clients connect from other devices; `localhost` otherwise |

There is no password or license key. Registration is self-service and the **first**
registration bootstraps the org.

## 1. Check the machine

```bash
docker version --format '{{.Server.Version}}'   # daemon must be reachable
docker compose version                          # compose v2, not docker-compose v1
nproc                                           # >= 2
free -g | awk 'NR==2{print $2}'                 # >= 4 (GB total)
df -h / | awk 'NR==2{print $4}'                 # >= 10G free
```

**Check:** all five return a value and meet the floor. If not: stop and report which.

On sizing, so you can judge a borderline machine: the image is ~1.2 GB and a running hive
sits around **1.7 GB** of resident memory with both models loaded. `docker-compose.yml`
sets `mem_limit: 8g`, but that is a **ceiling, not a reservation** — it exists so this
container falls over instead of dragging its neighbours down. 4 GB of host memory is
enough for a hive of one team; give it 8 GB if the machine also runs other things.

## 2. Start the hive

```bash
git clone https://github.com/nickozz714/Nectar.git
cd Nectar
docker compose pull && docker compose up -d
```

No `.env` is needed to start. The vault key generates itself and persists on the data
volume.

**Check:**

```bash
# First boot takes ~20-30s: Neo4j has to come up before the API answers. Bounded
# on purpose -- a wait without an end is how an agent hangs on a broken install.
for i in $(seq 1 40); do curl -sf localhost:8642/health >/dev/null && break; sleep 5; done
curl -sf localhost:8642/health || { docker compose logs --tail 50; exit 1; }
docker compose ps                      # both services up, hivemind healthy
```

Nothing after a minute or two: `docker compose logs -f` shows what it is waiting for.
`init_db` retries the database connection, so slow is normal and silent-forever is not.

### If clients connect from other devices

Put the machine's hostname or LAN IP in `.env` **before** the clients need TLS — the
self-signed certificate is issued on that name, and a TLS connection on any other name is
refused:

```bash
echo "NECTAR_HOST=192.168.1.10" >> .env      # the real hostname/IP
docker compose up -d caddy
```

Port `8642` is plain HTTP for the API and the recall hook; `8643` is the same thing over
TLS, which the MCP client needs.

## 3. Register the first account

```bash
API=http://localhost:8642

curl -s -X POST $API/register -H 'Content-Type: application/json' \
  -d "{\"name\":\"$ADMIN_NAME\",\"email\":\"$ADMIN_EMAIL\"}"
```

**Check:** the response contains `"role":"org_admin"` and a `token`. **Store that token** —
it is the only thing a client needs from then on, and the role is bound to it.

Does the response say an invite code is required? Then this hive already has an org and
someone registered before you. That is not an error; ask the user for an invite code
instead of starting over, and never wipe the volume to "get a clean start" — that is the
organisation's memory.

## 4. Connect a project

Nectar does **nothing** until a project opts in, so other projects and ad-hoc sessions stay
hive-free. From the project directory:

```bash
# any authed account can download the kit from its own hive
curl -sf -H "Authorization: Bearer $TOKEN" $API/install.zip -o hivemind-install.zip
unzip -o hivemind-install.zip && cd hivemind-install

# Linux, or a server reachable by hostname:
./install.sh "http://<host>:8642" "$TOKEN" "Anchor Topic,Another Topic"

# macOS with a LAN IP: add the SSH target as the 4th argument
./install.sh "http://192.168.1.10:8642" "$TOKEN" "Anchor Topic" "user@192.168.1.10"
```

**Check:** `claude mcp list` from that directory shows `hivemind` as connected, and
`.claude/settings.json` in the project now contains `HIVE_ENABLED` and the anchor topics.

> **macOS needs that 4th argument.** The Claude Code CLI cannot reach a private LAN IP
> (Local Network permission bug, claude-code #27828/#55169) and shows
> `FailedToOpenSocket`. The installer routes the MCP through a persistent `launchd`
> localhost SSH tunnel and points the client at `http://localhost:<port>/mcp`; the recall
> hook keeps using the LAN IP directly, because curl is not affected. It needs
> passwordless SSH to the server (`ssh-copy-id user@host`). On Linux, leave it off.
>
> Tools showing `FailedToOpenSocket` later means the tunnel is down, not that the hive is:
> `launchctl load ~/Library/LaunchAgents/com.hivemind.tunnel.plist`.

Anchor topics are a **preference, not a filter**: they tilt recall toward the subjects this
project cares about. Getting them roughly right is enough.

## 5. Add the other people

An org_admin mints an invite with **their own** token — no operator token involved:

```bash
curl -s -X POST $API/manage/invites -H "Authorization: Bearer $ORG_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"role":"member","uses":1}'
```

Share the returned `code`; the colleague registers with `"invite_code":"..."` and gets
their own token. Roles run `member` → `maintainer` → `org_admin`, and all of this is also
in the GUI's **Beheer** tab.

**Everyone gets their own token.** It carries their role, it can be rotated and revoked
individually, and the audit trail is worth something only if tokens are not shared.

## 6. Verify the whole thing works

```bash
# knowledge in (POST, JSON body)
curl -s -X POST $API/graph/remember -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"type":"memory","title":"This hive was installed and verified",
       "content":"Installed with RUNBOOK.md. The first write and read-back succeeded, so the write-gate, the local embeddings, the graph and retrieval all work.",
       "parent_topics":["Operations"]}'

# and back out (GET, query parameter -- there is no POST /search)
curl -s -G "$API/graph/search" --data-urlencode "q=installed and verified" \
  -H "Authorization: Bearer $TOKEN"
```

**Check:** the write returns a `uid` and the search finds that same `uid` back. Those two
calls exercise the entire chain — write-gate, local embeddings, graph, retrieval — and a
hive that passes them is working. The memory is a real, useful first entry, so leave it.

> Note the shapes: `/graph/remember` is a POST with a JSON body, `/graph/search` is a **GET**
> with a `q` parameter. They live under the `/graph` prefix; a bare `/remember` or `/search`
> is a 404. The full reference is in [docs/API.md](docs/API.md).

Then look at it: the GUI on `http://<host>:8642/ui` (log in with the token), and the Neo4j
Browser on `http://<host>:7474` if you want the raw graph.

## 7. Report back

Tell the user:

- the URL (`http://<host>:8642`, GUI on `/ui`);
- the **org_admin token**, and that it is the only credential there is;
- which projects you connected;
- **that the data volume is the organisation's memory.** Back it up
  (`./scripts/backup.sh` → `backups/hive-data-<stamp>.tgz`; it stops the container briefly
  for a consistent copy). If `SECRET_MASTER_KEY` was left to auto-generate it lives on that
  volume — losing the volume loses the vault with it.

## Known pitfalls

| Symptom | Cause | What to do |
| --- | --- | --- |
| Container restarts, exit 137 | Out of memory. `mem_limit` was once set to 3g and that killed it on the first real tool call | Neo4j is a JVM that sizes its heap from the **host's** memory, not the container's. Either leave the limit at 8g, or bound the JVM first (`NEO4J_server_memory_heap_max__size`, `pagecache_size`) and only then lower it |
| `/health` silent after `up` | First boot: Neo4j takes 20–30s | Wait, and watch `docker compose logs -f` |
| Caddy restarts in a loop | `NECTAR_HOST` empty inside the container | It must be set in `.env`; the Caddyfile reads it there, and an empty value makes `default_sni` a directive without an argument, which Caddy refuses |
| MCP tools `FailedToOpenSocket` on macOS | the SSH tunnel is down | `launchctl load ~/Library/LaunchAgents/com.hivemind.tunnel.plist` |
| UI loads but shows nothing | the token has no visible knowledge yet | Write something first, or check the token's scope |
| `No declared setting with name: URI` | Neo4j client env vars reached the Neo4j process | The bundled `start.sh` strips these; only relevant if you customised it |
| Data gone after running tests | The test suite is **destructive by design** | Always give tests their own Neo4j on a separate port. Never point them at the hive |

## What **not** to do

- Do not run a second instance against the same volume. Single-writer means single-writer.
- Do not expose `7474`/`7687` (Neo4j) to the internet. For remote access use a VPN or an
  authenticated reverse proxy with a real certificate, and point `HIVE_URL` at that.
- Do not wipe the data volume to resolve an error. It is the organisation's memory, and
  there is no second copy unless someone made one.
- Do not share one token between people. Mint an invite instead.
- Do not run the test suite against the hive.
