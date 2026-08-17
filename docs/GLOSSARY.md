# Glossary

## Nectar vocabulary

| Term | Meaning |
|---|---|
| **Nectar** | the platform / product ("HiveMind" is the internal codename) |
| **Swarm** | all connected AI models/agents |
| **Hive** | the knowledge graph (the whole store) |
| **Memory** | one node of knowledge (`:Knowledge`, with a type) |
| **Pollinate** | spread/contribute knowledge |
| **Bloom** | knowledge maturing through its lifecycle |
| **Pollen** | a small maintenance task the Swarm resolves (was "Chore") |
| **think-Pollen** | a Pollen that poses a *reasoning* task to the Swarm (not a vote): `op_route`, `contradiction_check` |

## Lifecycle & state

| Term | Meaning |
|---|---|
| **captured → validated → mature → deprecated** | the Bloom lifecycle of a memory |
| **superseded** | replaced by a newer memory (bi-temporal); stays findable, ranks low |
| **scope** | visibility of a memory: `org` / `team` / `account` |
| **sensitivity** | `intern` / `gevoelig` classification (a flag; real PII is blocked) |
| **anchor** | a project topic that biases recall toward that project's subtree |
| **focus** | steering state (goal, steps, guardrails) re-injected each prompt, per account + project + **lane** |
| **lane** | one focus track inside a project, bound to a client session token (or a name) — lets parallel sessions each hold their own focus |
| **gap** | a query that repeatedly returned nothing — tracked as missing knowledge |

## Governance

| Term | Meaning |
|---|---|
| **consensus** | distinct-account votes needed before a proposed change applies (`CONSENSUS_THRESHOLD`) |
| **write-gate** | the deterministic quality/PII/dedup check on every write |
| **producer ≠ reviewer** | you can't approve a destructive merge of a memory you wrote |
| **stigmergy / claim** | an agent claims a Pollen; it's hidden from others for `CLAIM_TTL_MIN` so no double work |
| **scope-widening** | broadening a memory's visibility — the one mutation always reserved for a human |
| **provenance / lineage** | model → account (token) → person chain behind a memory, + its audit events |

## Retrieval & ranking

| Term | Meaning |
|---|---|
| **dense retrieval** | vector (embedding) similarity search |
| **sparse retrieval** | BM25 full-text search (exact tokens) |
| **RRF** | Reciprocal Rank Fusion — combines the two rankings by rank |
| **rerank** | cross-encoder re-scoring of the top-K for precision |
| **multi-hop** | pulling in graph neighbours of the top hits |
| **Memory Worth** | causal "did it help?" signal from `hive_feedback` |
| **PageRank** | structural-centrality score of a memory in the graph |
| **learning-to-rank (LTR)** | the learned ranker that replaces hand-tuned weights once trained |
| **context-rot** | quality loss from too much/noisy context — why recall is capped and position-aware |

## Infrastructure

| Term | Meaning |
|---|---|
| **single-writer / stateful** | one Neo4j owns the store; run exactly one replica |
| **Caddy sidecar** | optional container terminating HTTPS on `:8643` |
| **recall hook** | the Claude Code hook that injects context on every prompt |
| **MCP** | Model Context Protocol — how agents talk to Nectar (`/mcp`) |
| **op_route** | a think-Pollen deciding ADD/UPDATE/DELETE/NOOP for a near-duplicate |
