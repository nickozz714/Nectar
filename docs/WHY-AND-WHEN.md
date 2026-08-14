# Why, When & Value

## The problem it solves

AI agents are stateless. Every session starts from zero: the same context is re-explained, the same
mistakes are repeated, decisions made last week are unknown, and knowledge one teammate's agent
learned is invisible to everyone else's. Notes in a wiki don't help — the agent doesn't read them at
the right moment, and they rot.

**Nectar is the shared, self-maintaining memory that fixes this.** Every connected agent
automatically gets the right knowledge on every prompt, can contribute new knowledge, and helps keep
the whole thing healthy — with no human curation.

## Value for organisations

- **Compounding knowledge, not repeated work.** What one agent learns, every agent knows next time.
  Decisions, conventions, gotchas and workflows accumulate instead of evaporating at session end.
- **Consistency across a team/fleet.** Ten engineers' agents pull from one source of truth, so they
  follow the same conventions and don't contradict each other.
- **Governance & auditability.** Who wrote what, via which identity, and what happened to it since —
  a full provenance and audit trail. Sensitive knowledge is flagged; scope-widening needs a human.
- **Self-maintaining.** The Swarm dedupes, relates, re-homes, supersedes and reconciles
  contradictions in the background. The brain gets *cleaner* over time, not messier.
- **Fully self-hosted & private.** Runs in one container on your own hardware/cloud. No data leaves
  your network; no per-token cloud bill for the memory layer.
- **Client-agnostic.** Any MCP-capable client (Claude Code, Cursor, Cline, your own agent) plugs in.
- **It grows a world model around your knowledge.** With Cognition enabled, the hive researches the
  unfamiliar entities your memories mention and weaves the findings back into the graph (see below).

## Seeing the mind — the 3D interface

Since 2026-08-14 Nectar has a second front door, and it is the default: **`/ui/mind`** renders the
mind as a *place* instead of a page. Topics are named stars in a galaxy (a "netwerk" mode shows the
whole organism at once); click a star and you fly into its system, where the knowledge orbits its
topic and a **cockpit** opens — the focused node centre-stage with its parents, children and related
knowledge as clickable cards, so you read and *navigate* at the same time. Every other function
lives inside the same HUD as a deck: the Pollinate queue (with who-claimed/who-resolved), human
review, the governance dashboard with its distributions and audit trail, and the full admin surface
(insight, maintenance scans, settings, access, backup, packages). Search is hybrid: title hits are
instant, semantic content hits merge in a beat later. Selecting anything dims the rest of the brain
to its direct wiring; Esc peels back layer by layer. The classic tabbed GUI remains fully supported
— `Org.default_ui` decides where members land, and each interface links to the other.

## A world model around your knowledge — Cognition

Organisational knowledge never exists in a vacuum: a migration memory mentions a vendor, a data
model references a product, an engineering note names a library. **Cognition** (opt-in per org,
default off) makes the hive *curious about exactly those gaps*. When a new memory passes the
write-gate, the server files a research task — a Pollen like any other. A swarm agent picks it up,
checks what the hive already knows, looks the rest up on the web, and writes compact, source-linked
**glossary entries** tagged `world-knowledge`, connected to the memory that raised them. Curiosity
is bounded by construction (a per-job memory budget, a two-round depth limit enforced server-side,
a daily cap) and everything passes the same write-gate and provenance rules as human knowledge.

The effect is a **world model that grows around the org's own knowledge** — built from what the
organisation actually works on, not from a generic encyclopedia. In our own hive, memories about a
municipal data platform quietly gained researched context on *Centric* and *PinkRoccade's
iSamenleving* (the vendors behind the source systems), a client memory grew a profile of *Beeminds*
and its Intelligenthive platform, and engineering notes sprouted entries for *httpx*, *Plex* and
*Spotify* — so recall on any of those names now also surfaces the org memories that mention them.
Design and mechanics: `docs/COGNITION.md`.

## When to use it

**Use Nectar when:**
- Multiple people or multiple agents work on shared, evolving knowledge (a codebase, a data
  platform, a set of client projects).
- Knowledge has a *lifetime*: decisions get superseded, conventions change, lessons are learned.
- You need the memory to be **private** and **auditable** (regulated data, client work, IP).
- You want agents to *maintain* the knowledge, not just retrieve it.

**Don't reach for it when:**
- You need a one-shot document Q&A over a static corpus — a plain RAG/vector store is simpler.
- Everything fits in the model's context window and never changes — just paste it.
- You need multi-region HA/failover at scale — the single-container design is deliberately not that
  (see DEPLOYMENT for the ceiling).

---

## The landscape — a crowded, fast-moving category

"Agent memory" is an established category in 2026, with several well-resourced products and many
open-source projects. Nectar is a *differentiated take, not a first-mover* — and being honest about
that matters. The main reference points:

- **Mem0** — managed, drop-in memory API; strongest for user *personalisation*. Cloud-first.
- **Zep / Graphiti** — a **bi-temporal knowledge graph** (every fact tagged valid-from / valid-to);
  the closest to Nectar's truth-over-time model, but more managed and benchmark-driven.
- **Letta (MemGPT)** — an agent with tiered, self-editing memory blocks managed via tools.
- **LangMem / Cognee / Cloudflare** and a broad ecosystem (see *Awesome-Agent-Memory*).
- **Neo4j-labs `meta-knowledge-graph` / `agent-memory`** — Neo4j's own graph-native, MCP-based,
  self-improving memory with a contradiction gate + human review. **Architecturally the closest** to
  Nectar.

## How Nectar differs (honestly)

| Dimension | Mem0 | Zep / Graphiti | Neo4j-labs MKG | **Nectar** |
|---|---|---|---|---|
| Deploy | cloud SaaS | cloud / self-host | self-host | **self-host, one container** |
| Who *judges* what to keep/merge | LLM extraction | LLM extraction | an LLM extractor + LLM judge | **the connected agents (swarm) + deterministic detection; no server-side LLM** |
| Maintenance model | auto-extract | auto-extract | single-LLM gate + human review | **swarm-resolved Pollen: consensus, producer≠reviewer, human-gated scope-widening** |
| Multi-tenant (org/team/person) | limited | limited | no | **yes, enforced per query** |
| Secrets vault + audit + provenance | — | — | partial | **yes** |
| Fully local / no cloud LLM | no | usually no | needs your LLM keys | **yes (local embeddings + rerank)** |
| Managed / HA / benchmarks | yes | yes | — | no (single-writer by design) |

**Where Nectar is genuinely different:** it makes upkeep a *governed, multi-agent, largely LLM-free*
process — the connected agents themselves dedup, relate and reconcile contradictions under consensus,
rather than one server-side LLM deciding — and it ships fully local + multi-tenant with a vault and
audit. That combination (local + swarm-governed + multi-tenant governance) is its niche.

**Where the others win:** managed convenience, scale/HA, funding, benchmarks, community and
integrations. If you want turnkey and don't care about self-hosting or agent-driven governance, a
managed product is simpler. Nectar trades scale-out and polish for **privacy, governance, and a brain
the swarm curates itself**.


---

## Studies & design basis (why these choices)

- **Hybrid + RRF** — combining dense and sparse retrieval and fusing by *rank* (Reciprocal Rank
  Fusion, Cormack et al.) is a robust, tuning-free way to get both meaning and exact tokens.
- **Cross-encoder reranking** — the standard "retrieve-then-rerank" two-stage IR pattern; the
  cross-encoder's joint encoding is markedly more precise than bi-encoder similarity for the top-K.
- **"Lost in the middle"** (Liu et al.) — models attend most to the start and end of the context;
  Nectar caps injected memories and puts the strongest at the ends.
- **Bi-temporal / supersession** — treat knowledge like slowly-changing dimensions: never destroy,
  supersede; keep history findable but ranked down.
- **Stigmergy & swarm maintenance** — indirect coordination (claim-with-TTL, one contextual task per
  visit) lets many independent agents maintain a shared structure without central locking.
- **Server-side LLM-free** — keep the server deterministic and private; delegate judgement to the
  Swarm via *think-Pollen*. Detection is cheap and deterministic; judgement is the model's job.

The full mechanics and formulas are in **[ML-AND-ALGORITHMS.md](ML-AND-ALGORITHMS.md)**; the
product-design rationale is in **[../DESIGN.md](../DESIGN.md)**.
