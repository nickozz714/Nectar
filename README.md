# Nectar 🍯

**The shared brain for your AI agents.** One graph database that hands every connected AI the
right knowledge on every prompt, cleans itself up, and gets smarter over time. It runs **fully
local in one container** (Neo4j + API + local models) — no cloud, no data leaving your network.

- **New here? → [INSTALL.md](INSTALL.md)** — zero to a working hive in ~5 minutes.
- **How it works & why → [DESIGN.md](DESIGN.md)**
- **Deep dive → [docs/](docs/)** — architecture diagrams, ML & formulas, deployment (server/Azure/OpenShift), security, Cypher cookbook, API/MCP reference, and more.

> This README is kept up to date as a plain-language overview of what's inside. A shareable
> version lives as an artifact; the two are kept in sync.

---

## In one sentence

Every connected AI automatically gets relevant knowledge, can add new knowledge, and helps
maintain the brain — without you doing anything.

## What's inside

### Remembering & finding it back — the core
- **Smart search** — combines meaning *and* exact words (symbols, error codes, paths), so it
  always finds the right thing (hybrid dense + BM25, fused).
- **Reranking** — a small local model re-weighs the best hits precisely for sharper results.
- **Structural importance** — knowledge that is well-connected to other knowledge (PageRank)
  counts a little heavier.
- **Learns from feedback** — as agents report what helped, the ranker learns the best weighting
  itself, so search order improves over time (learning-to-rank).
- **Short & focused** — only the strongest few pieces are injected, no noise that distracts
  the model.
- **Truth over time** — a newer decision supersedes the old one; the old stays findable but
  sinks in ranking.

### Knowledge that matures
- **Lifecycle** — captured → validated → mature → deprecated. Proven knowledge rises on its own.
- **Importance pin** — mark a memory as important or trivial.
- **Did it help?** — agents report whether a recalled memory was useful; what helps rises,
  what misleads sinks (causal "Memory Worth").
- **Staleness** — old-but-heavily-used knowledge gets an automatic "is this still correct?" check.

### The swarm does the upkeep
- **Pollen (tasks)** — every visit hands an agent one relevant maintenance task; together they
  keep the brain healthy.
- **Voting** — changes only apply with enough **independent** agreement; you set the threshold.
- **No duplicate work** — an agent "claims" a task; others then don't see it (stigmergy).
- **Self-tidying** — loose knowledge gets a logical home proposed; empty searches become
  tracked knowledge gaps.
- **Suggests connections** — spots memories that probably belong together and proposes linking
  them (link prediction) — as a suggestion, never automatically.
- **Catches contradictions** — spots two memories that look alike but may state opposite things
  (e.g. a different decision for the same topic); a *different* agent judges whether they really
  conflict, and if so the outdated one is superseded — the current truth wins.
- **Thinking together** — for two near-duplicate memories a *different* agent decides how they
  merge — never rubber-stamping your own work.

### The window (GUI, at `/ui`)
- **Living graph** — click through the brain as a sci-fi network; focus on what you click,
  zoom, history.
- **Insight** — totals per lifecycle phase, most/never used, knowledge gaps at a glance.
- **Works on mobile.**
- **Names only** — you always work with recognizable, searchable names, never technical ids.

### Foundation
- **Backup & restore** — export and restore the whole brain as one file.
- **Secure** — knowledge is scoped per org / team / person; secrets live in a separate vault,
  kept out of recall.
- **Local** — all the "smart" models run locally on the server. No cloud.

## The Nectar vocabulary

| Term | Meaning |
|---|---|
| **Nectar** | the platform |
| **Swarm** | all connected AI models |
| **Hive** | the knowledge graph |
| **Memory** | a piece of knowledge |
| **Pollinate** | spread knowledge |
| **Bloom** | knowledge that matures |
| **Pollen** | a maintenance task |

---

## Setup

Runs as one Docker Compose stack (Neo4j + API + local models in one container, with an
optional HTTPS sidecar).

```bash
# 1. Configure — copy the example env and set at least a strong Neo4j password
cp server/.env.example .env
#   edit .env: NEO4J_PASSWORD=... (required) · HIVE_ORG_NAME=... · leave the rest to start

# 2. Build & run
docker compose up -d --build

# 3. Wait until healthy, then open the GUI and create the first account (becomes org_admin)
open http://localhost:8642/ui
```

Ports:

| Port | What |
|---|---|
| `8642` | API + MCP + GUI (`/ui`) |
| `8643` | same, over HTTPS (Caddy sidecar — for MCP clients that need TLS) |
| `7474` | Neo4j Browser (a window into the raw graph) |

Key settings in `.env` (all have safe defaults — see `server/.env.example`):

| Var | Meaning |
|---|---|
| `NEO4J_PASSWORD` | **required** — the graph store password |
| `HIVE_ORG_NAME` | name of the org created by the first sign-up |
| `SECRET_MASTER_KEY` | Fernet key for the vault (auto-generated + persisted if empty) |
| `CONSENSUS_THRESHOLD` | independent votes before a change applies (set `1` for a solo/small swarm) |
| `RERANK_ENABLED` | local cross-encoder reranking on/off (default on) |
| `EMBEDDINGS_*` | local embedding model config (local by default, no cloud) |
| `ENTRA_*` | optional Microsoft SSO (leave blank to disable) |

### Connect a Claude Code CLI

Any project opts in with the bundled plugin — a recall hook (injects knowledge every prompt),
a skill, and secret/update helpers. Download the install kit from the GUI (Beheer →
install-zip) or see **[INSTALL.md](INSTALL.md)** for the exact steps.

### Connect any other MCP client (client-agnostic)

Nectar is a **standard MCP server** — the whole brain (search, remember, chores, feedback,
focus, skills, secrets) is available to **any MCP-capable client** (Cursor, Cline, Windsurf,
your own agent, …), not just Claude Code. Point the client at the MCP endpoint with an account
token:

```jsonc
// generic MCP client config
{
  "mcpServers": {
    "nectar": {
      "url": "https://<host>:8643/mcp",       // HTTPS via the Caddy sidecar
      "headers": { "Authorization": "Bearer <your account token>" }
    }
  }
}
```

The one Claude-Code-specific nicety is *automatic* recall on every prompt (via its hook). Every
other client gets the same experience **on demand**: have the model call **`hive_recall("<your
task>")`** at the start of a task — it returns the exact same context block (active focus +
standing instructions + top-ranked memories + one Pollen). Then `hive_remember` to write and
`hive_feedback` on what helped. The MCP server's own instructions tell connecting models to do
this, so it works out of the box.

### Deploy an update

```bash
# from the repo root, against the deploy host
rsync -az --exclude __pycache__ server/src <host>:/path/to/Nectar/server/
ssh <host> 'cd /path/to/Nectar && docker compose up -d --build hivemind'
```

Data migrations (label renames, Bloom backfill, index creation) run **idempotently on startup**,
so deploying is all it takes — no manual database steps.

---

## Under the hood

Single **Neo4j 5** store (graph + native vector index + BM25 full-text) behind **FastAPI +
fastmcp**, layered `routers → services → repository → components`. Embeddings and reranking are
**local** (fastembed, ONNX/CPU). Any heavier LLM reasoning is pushed to the connected **swarm**
(the agents themselves), never a server-side LLM — see [DESIGN.md](DESIGN.md).
