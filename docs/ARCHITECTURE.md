# Architecture

Nectar is one **stateful container**: a Neo4j 5 database, a FastAPI + fastmcp application, and small
local ML models (embeddings + reranker), all in a single image. There is no separate app tier, no
message bus, no external model service. That simplicity is deliberate — it makes the whole brain
trivially self-hostable and keeps every byte of data on your own machine.

- **Language/stack:** Python 3.12, FastAPI, [fastmcp](https://github.com/jlowin/fastmcp), Neo4j 5
  Community, [fastembed](https://github.com/qdrant/fastembed) (ONNX, CPU — no PyTorch).
- **Layering:** `routers/ → services/ → repository/ → components/` (HTTP/MCP surface → business
  logic → Cypher → cross-cutting config/db/embeddings).
- **Single store:** Neo4j holds *everything* — the knowledge graph, tenancy, the secrets vault,
  the audit trail, Pollen, plus a **native vector index** and a **BM25 full-text index**. No
  separate vector database.

---

## 1. System context

```mermaid
flowchart LR
  subgraph Clients["Swarm — connected AI clients"]
    CC["Claude Code CLI<br/>(recall hook + plugin)"]
    OTHER["Any MCP client<br/>Cursor · Cline · custom agent"]
    HUMAN["Human<br/>(browser)"]
  end

  subgraph Nectar["Nectar container"]
    API["FastAPI + fastmcp<br/>:8000 (→ :8642)"]
    EMB["fastembed<br/>embeddings + reranker<br/>(in-process, ONNX/CPU)"]
    NEO[("Neo4j 5<br/>graph · vectors · BM25<br/>vault · audit · Pollen")]
    API <--> EMB
    API <--> NEO
  end

  CADDY["Caddy sidecar<br/>HTTPS :8643"]

  CC -- "MCP + recall (HTTP)" --> API
  OTHER -- "MCP (HTTP/SSE)" --> API
  HUMAN -- "GUI /ui + Neo4j Browser :7474" --> API
  HUMAN -. "TLS" .-> CADDY --> API
```

**Ports**

| Port | Surface | Notes |
|---|---|---|
| `8642` | HTTP API + MCP (`/mcp`) + GUI (`/ui`) | The one port clients use. (uvicorn listens on `8000` inside; mapped out as `8642`.) |
| `8643` | Same, over HTTPS | Optional Caddy sidecar terminating TLS (self-signed or real). For MCP clients that require TLS. |
| `7474` | Neo4j Browser | A window on the raw graph. **Do not expose publicly.** |
| `7687` | Bolt | Neo4j's binary protocol. Internal; open only to trusted tooling over a tunnel/VPN. |

---

## 2. Components inside the container

```mermaid
flowchart TB
  subgraph routers["routers/ — HTTP + MCP surface"]
    R1["graph_api · recall · manage · admin"]
    R2["auth · entra · signup · skills · secrets · backup · attachments"]
    MCP["tools/registry.py — MCP tools (hive_*)"]
  end
  subgraph services["services/ — business logic"]
    S1["search_service (retrieval + ranking)"]
    S2["memory_service (write-gate)"]
    S3["governance_service · curation_service"]
    S4["recall_service · ltr_service · reranker"]
  end
  subgraph repository["repository/ — Cypher"]
    P1["graph_repo · governance_repo"]
    P2["tenancy_repo · audit_repo · focus_repo · registration_repo"]
  end
  subgraph components["components/"]
    C1["config (all tuning knobs)"]
    C2["db (driver + startup migrations)"]
    C3["embeddings (fastembed)"]
  end
  routers --> services --> repository --> C2
  services --> C3
  services --> C1
  C2 --> NEO[("Neo4j")]
```

Startup runs **idempotent migrations** in `components/db.py`: it creates the `knowledge_uid`
constraint, the `knowledge_embedding` **vector index** (384-dim, cosine) and the
`knowledge_fulltext` **BM25 index**, and backfills legacy data (e.g. the Bloom lifecycle and the
`:Chore`→`:Pollen` relabel). Deploying is therefore just "ship code + restart" — no manual DB steps.

---

## 3. The read path — recall & retrieval

Every prompt triggers a deterministic recall. There is **no LLM in this path** — only a local
embedding model, a local cross-encoder, and arithmetic.

```mermaid
flowchart TB
  Q["query (+ anchors, project)"] --> E["embed query<br/>(fastembed, 384-d)"]
  E --> V["vector candidates<br/>knowledge_embedding index"]
  Q --> B["BM25 candidates<br/>knowledge_fulltext index"]
  V --> RRF["Reciprocal Rank Fusion<br/>(k = 60)"]
  B --> RRF
  RRF --> HOP["1-hop multi-hop expansion<br/>(neighbours of top anchors)"]
  HOP --> RR["cross-encoder rerank<br/>(top-40, local ms-marco MiniLM)"]
  RR --> SC["feature scoring<br/>dot(features, weights)  ·or·  learned LTR"]
  SC --> CAP["relevance cap + position-aware injection<br/>(max 6, floor 0.45, strong ends)"]
  CAP --> OUT["context block<br/>focus + system instructions + memories + one Pollen"]
```

The scoring features and their weights (freshness/decay, Bloom, importance, Memory Worth, PageRank,
supersession penalty, anchor/decision/learning boosts) and the exact formulas are in
**[ML-AND-ALGORITHMS.md](ML-AND-ALGORITHMS.md)**.

---

## 4. The write path — the write-gate

New knowledge is written directly (agents are trusted to *add*), but a deterministic gate protects
quality and prevents sprawl. Editing *existing* knowledge is never direct — it is consensus-gated
(§5).

```mermaid
flowchart TB
  W["hive_remember(type, title, content, scope)"] --> PII{"PII / quality<br/>regex + min length"}
  PII -- blocked --> REJ["rejected (reason returned)"]
  PII -- ok --> EMB["embed(title + content)"]
  EMB --> DUP{"nearest existing<br/>cosine similarity"}
  DUP -- "≥ 0.92" --> TOUCH["treat as duplicate<br/>touch existing (no new node)"]
  DUP -- "0.85 – 0.92 (grey band)" --> STORE1["store + file op_route think-Pollen<br/>(swarm decides ADD/UPDATE/DELETE/NOOP)"]
  DUP -- "< 0.85" --> STORE2["store new memory"]
  STORE1 --> TOPIC
  STORE2 --> TOPIC{"topic reuse<br/>≥ 0.85 → attach to existing topic<br/>else create topic"}
  TOPIC --> DONE["node created · sensitivity classified · audited"]
```

Thresholds (`DEDUP_SIMILARITY_THRESHOLD` 0.92, `DEDUP_REVIEW_THRESHOLD` 0.85,
`TOPIC_SIMILARITY_THRESHOLD` 0.85, `MIN_TITLE_LENGTH` 8, `MIN_CONTENT_LENGTH` 40) live in
`components/config.py` and are shown read-only in the GUI's **Beheer → Instellingen**.

---

## 5. Governance — how the Swarm maintains the Hive

Mutations to existing knowledge and structural upkeep flow through **Pollen** (small tasks). Two
kinds exist: **consensus Pollen** (a proposed change that needs independent votes) and
**think-Pollen** (a reasoning task the server hands to the Swarm).

```mermaid
flowchart TB
  subgraph produce["produced by"]
    SUG["hive_suggest (an agent proposes an edit/invalidate/…)"]
    SCAN["background scans: tidy · staleness · linkpred · contradiction · dedup grey-band"]
  end
  SUG --> OPEN["Pollen: open"]
  SCAN --> READY0["Pollen: ready (think-Pollen: op_route / contradiction_check)"]
  OPEN --> VOTES{"votes ≥ CONSENSUS_THRESHOLD<br/>(distinct accounts)"}
  VOTES -- yes --> READY["Pollen: ready"]
  VOTES -- "scope widening" --> HUMAN["awaiting_human (review queue)"]
  READY --> RESOLVE["a Swarm member resolves it"]
  READY0 --> RESOLVE
  HUMAN --> HR["a human approves/rejects"]
  RESOLVE --> APPLY["apply: link · archive · supersede · merge · relate"]
  HR --> APPLY
  APPLY --> AUDIT["audited (append-only)"]
```

Safeguards: consensus counts **distinct accounts** (correlation-aware); **scope-widening** always
escalates to a human; for a near-duplicate merge (`op_route`) the **producer ≠ reviewer** (you can't
rubber-stamp your own write); a claimed Pollen is hidden from other agents for `CLAIM_TTL_MIN`
minutes (stigmergy) so two agents don't do the same task.

---

## 6. Deployment topology (reference: own server)

```mermaid
flowchart LR
  subgraph host["Docker host (your server)"]
    direction TB
    NECTAR["nectar container<br/>Neo4j + API + models"]
    CADDY["caddy sidecar (TLS)"]
    VOL[("volume: /data<br/>Neo4j store + vault key")]
    NECTAR --- VOL
    CADDY --> NECTAR
  end
  LAN["LAN clients"] --> NECTAR
  REMOTE["remote clients"] -. "VPN / reverse proxy" .-> CADDY
```

The container is **stateful and single-writer** (Neo4j is embedded). This is the single most
important operational fact: **you run exactly one replica**, and the `/data` volume must persist.
The implications for Azure Container Apps and OpenShift/Kubernetes are covered in
**[DEPLOYMENT.md](DEPLOYMENT.md)**.

---

## 7. Design decisions worth knowing

- **Single container, single store.** Neo4j does graph + vectors + full-text + tenancy + vault +
  audit. One dependency to run and back up. Trade-off: no horizontal scale-out (see DEPLOYMENT).
- **Server stays LLM-free.** Embeddings and reranking are small local ONNX models; any real
  reasoning is delegated to the Swarm via think-Pollen. No prompt or memory is ever sent to a
  cloud LLM by the server itself.
- **Everything is bi-temporal & non-destructive.** Nothing is hard-deleted by the Swarm — memories
  are archived or superseded; the old truth stays findable but sinks in ranking.
- **Deterministic where it can be, delegated where it can't.** Detection (what *might* be a
  duplicate/contradiction/gap) is deterministic and cheap; *judgement* is the Swarm's.
