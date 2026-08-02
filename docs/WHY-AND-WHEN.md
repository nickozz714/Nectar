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

## GAP analysis — how it compares

| Capability | Plain vector DB / RAG | Generic agent-memory (e.g. Mem0/Zep-style) | **Nectar** |
|---|---|---|---|
| Semantic retrieval | ✅ | ✅ | ✅ (dense) |
| Exact-token retrieval (symbols, errors, paths) | usually ✗ | varies | ✅ (BM25 + RRF hybrid) |
| Graph relationships / multi-hop | ✗ | some | ✅ (topics DAG, RELATES, 1-hop expand) |
| Cross-encoder reranking | rare | rare | ✅ (local) |
| Truth-over-time (supersession) | ✗ | rare | ✅ (bi-temporal) |
| Maturity/lifecycle of knowledge | ✗ | ✗ | ✅ (Bloom) |
| Learns ranking from feedback | ✗ | rare | ✅ (learning-to-rank) |
| **Self-maintenance by the agents** | ✗ | ✗ | ✅ (Pollen: dedup, relate, stale, contradiction) |
| Consensus before mutating knowledge | ✗ | ✗ | ✅ (distinct-account votes) |
| Multi-tenant scope (org/team/person) | bolt-on | varies | ✅ (native, enforced per query) |
| Secrets vault (encrypted, audited) | ✗ | ✗ | ✅ (Fernet, REST-only) |
| Audit trail + provenance | ✗ | rare | ✅ (append-only + lineage) |
| Fully local / no cloud LLM | depends | usually cloud | ✅ (local models only) |
| Runs in one self-hostable container | varies | usually SaaS | ✅ |
| Horizontal scale-out / HA | ✅ (managed DBs) | ✅ (SaaS) | ✗ (single-writer by design) |

**Where Nectar wins:** it treats memory as a *living, governed graph* maintained by the agents
themselves, fully on your own infrastructure — not a passive vector index you query.

**Where alternatives win:** managed SaaS memory and cloud vector DBs give you turnkey scale/HA and
zero ops. If you need massive multi-region throughput and don't care about self-hosting or
self-maintenance, those are simpler. Nectar trades scale-out for **privacy, governance, and a brain
that curates itself**.

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
