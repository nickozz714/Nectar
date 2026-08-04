# Nectar — Documentation

> **Nectar** is a self-hosted, multi-tenant **organisational memory** for AI
> agents: one Neo4j-backed graph that hands every connected model the right knowledge on every
> prompt, maintains itself through a swarm of the agents themselves, and runs **fully local** — no
> cloud, no data leaving your network.

This folder is the deep-dive documentation. For a 5-minute start use the root
**[INSTALL.md](../INSTALL.md)**; for the plain-language overview use the root
**[README.md](../README.md)**.

## Map

| Doc | What it covers |
|---|---|
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System, component, retrieval, write-gate, governance and deployment **diagrams** (Mermaid) + how the pieces fit. |
| **[WHY-AND-WHEN.md](WHY-AND-WHEN.md)** | The value for organisations, when to use it (and when not), and a **GAP analysis** vs. vector DBs / RAG / other agent-memory products. |
| **[ML-AND-ALGORITHMS.md](ML-AND-ALGORITHMS.md)** | Every model & **formula**: hybrid retrieval + RRF, cross-encoder rerank, PageRank, learning-to-rank, link prediction, decay, Bloom, Memory Worth, the ranking function. |
| **[DATA-MODEL.md](DATA-MODEL.md)** | The graph **schema**: node labels, relationships, properties, indexes. |
| **[NEO4J.md](NEO4J.md)** | Reaching and using the **Neo4j server directly** + a **Cypher cookbook** of frequently used queries. |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Own server (Docker Compose) vs **Azure Container Apps** vs **OpenShift/Kubernetes** — with the trade-offs of a stateful single-container design. |
| **[SECURITY.md](SECURITY.md)** | Data safety & security-in-use: tenancy/scope, auth, the encrypted vault, PII gate, audit, network exposure, threat model + hardening checklist. |
| **[API.md](API.md)** | The full **HTTP API** and **MCP tool** reference. |
| **[OPERATIONS.md](OPERATIONS.md)** | Runbook: backup/restore, the maintenance scans, tuning, upgrading, observability. |
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | FAQ and the known gotchas (macOS MCP, iOS Safari, Metrics-App timezones, …). |
| **[GLOSSARY.md](GLOSSARY.md)** | The Nectar vocabulary (Swarm, Hive, Pollen, Bloom, …) and technical terms. |

## The one-paragraph mental model

Every connected AI (the **Swarm**) reads from and writes to a single shared graph (the **Hive**).
On every prompt a deterministic **recall** step injects the most relevant **memories** plus the
active project focus and standing instructions. Agents write new knowledge through a **write-gate**
(quality, PII, dedup). Changes to existing knowledge are **consensus-gated** across independent
agents. The brain maintains itself: background scans open **Pollen** (small maintenance tasks) that
visiting agents resolve — deduping, relating, re-homing, superseding, and reasoning about
contradictions. All the "smart" bits (embeddings, reranking) run as **small local models**; any
heavier reasoning is pushed to the Swarm, never to a server-side cloud LLM.

## Vocabulary at a glance

| Term | Meaning |
|---|---|
| **Nectar** | the platform / product |
| **Swarm** | all connected AI models |
| **Hive** | the knowledge graph |
| **Memory** | one node of knowledge |
| **Pollinate** | spread knowledge |
| **Bloom** | knowledge maturing (captured → validated → mature → deprecated) |
| **Pollen** | a maintenance task the Swarm resolves |

Full list in **[GLOSSARY.md](GLOSSARY.md)**.
