# HiveMind — Design

> The shared mind of an organization. Claude models are the **bees**; HiveMind is the **hive**
> they collectively maintain. At the same time it is a *hive mind* in the Stranger Things
> sense: one shared memory all connected minds draw from.

## 1. Vision

Organizations do a lot of the same work but have no way to share, frame and organize
**work processes, experiences (memories) and skills** org-wide. HiveMind is a standalone
product: a shared "company mind" that a Claude Code CLI (or any client) logs into with an
**account token**. The token gives scoped access to the org's memories, processes, skills
and account-bound secrets. It must genuinely *work* as a memory — like a human brain, not
like a document dump.

Explicitly **not** part of ND3X or any other backend; clients connect outbound with token
auth. Reuses house *patterns* only (layered FastAPI, fastmcp behind a bearer gate,
K3YVAULT-style vault thinking) — no code coupling.

## 2. Architecture — five blocks

1. **Accounts & auth** — org → teams → accounts, each account has opaque tokens
   (SHA-256 hashed at rest, revocable, optional expiry). Token scope defines which
   memories/skills/secrets are visible. Full hierarchy from day one.
   **Roles** (decided 2026-07-25): `member` (read, write, suggest/vote) →
   `maintainer` (also resolve swarm chores) → `org_admin` (also human review of
   scope-widening, with their own token via `/review`). Suggesting stays open to all —
   votes are the signal; *executing* mutations is delegated deliberately. The infra
   `ADMIN_TOKEN` remains for provisioning only.
2. **The Mind** — a knowledge graph with vector recall (GraphRAG).
3. **Skill registry** — skills as shareable units in the Claude Code skill format.
4. **Secrets vault** — fresh component (not K3YVAULT), per-secret grants, audit on every read.
5. **MCP gateway** — the only surface the CLI sees.

## 3. Stack (decided)

| Concern | Choice | Why |
|---|---|---|
| Database | **Neo4j 5 (community)** — one store for graph, vectors, tenancy, vault, audit, chores | Cypher makes DAG traversal & promotion natural; native vector index; Neo4j Browser = visual window into the mind |
| API | Python, FastAPI, layered `routers → services → repository` | house convention |
| MCP | fastmcp mounted in the FastAPI app, bearer-gated per call | house convention |
| Embeddings | **local-only by default** (decided 2026-07-25): in-process fastembed (ONNX, no torch), multilingual MiniLM (384d), model baked into the image at build time — **no cloud model is ever required**, the stack runs autonomously/offline inside an organization. An OpenAI-compatible `EMBEDDINGS_BASE_URL` can override local mode | org knowledge must not leak to a cloud API; graceful degradation to word-based search when disabled |
| Secrets crypto | Fernet (symmetric), master key from env | simple, rotatable |
| Deploy | **one container** (decided 2026-07-25): a single image bundling Neo4j + API + embeddings (`Dockerfile` at repo root, `start.sh` runs both), data on one volume | house style (cf. SerieTracker); one thing to deploy, back up and move |

**Server is deterministic ("dumb"); all judgement lives in the bees.** The server does
storage, ranking, thresholds and queues. The write-gate performs only deterministic checks
(PII regexes, embedding-similarity dedup). Curation judgement ("is this reusable company
knowledge?") is client-side via skill instructions, corrected over time by swarm consensus.

## 4. The Mind — graph model

- Every knowledge item is a node with label `:Knowledge` plus a type label:
  `Topic, Memory, Process, Workflow, Skill, Convention, Decision, Glossary`.
  Workflows (step-by-step or executable procedures, optionally file-backed via
  `workflow_put`) can stand alone under a topic or be linked under a skill — the graph
  handles both.
- **Top-down structure**: topics sit at the top (subjects like *Data Modelling*, but
  projects like *Swinkels* or systems like *IntelligentHive* are equally valid top-level
  topics). Memories link **under** topics via `[:CONTAINS]`; free association via
  `[:RELATES]`.
- **Topics form a DAG, not a tree — a node can have multiple parents.** A Fabric-werkwijze
  learned at Swinkels lives under `Swinkels → Fabric`; when generic enough it is
  **promoted = re-linked** under the generic `Fabric werkwijzen` topic *while keeping its
  origin link*. No moves, no copies — extra edges. Knowledge transfers across contexts the
  way a human applies Process A from topic X to topic Y.
- **Scoping/tenancy on every node**: `scope ∈ {org, team, account}` + `team_uid`/`account_uid`.
  Visibility filter is applied in every query. Nodes are never hard-deleted by the swarm;
  invalidation sets `archived = true`.

### Project anchoring
A local project declares which hive topics it leans on via `HIVE_ANCHORS`
(comma-separated topic titles, e.g. `Swinkels,Fabric werkwijzen`), set per project in
`.claude/settings.json` `env` — the plugin's `hive-init` script writes it and suggests a
CLAUDE.md block. Every Claude Code session started in that directory inherits it; the
recall hook passes it on every prompt.

**Anchors are a preference, not a filter** (decided 2026-07-25): nodes inside the
anchored topic subtree (`CONTAINS*` descendants) get a ranking boost (`ANCHOR_BOOST`);
everything else stays findable, just ranked lower. Working on Swinkels you see
Swinkels/Fabric knowledge first, but a relevant Gemeente Krimpenerwaard memory can still
surface — cross-context transfer must never be blocked by scoping.

## 5. Freshness & decay

Memories **age when unused and rejuvenate when used** (touch-on-read: every retrieval
updates `last_used` and `use_count`). Ranking = semantic similarity × W_sem + freshness ×
W_fresh, where freshness = `0.5 ^ (days_since_last_use / half_life)`.

Guardrails (decided):
- Decay affects **ranking, not findability** — old ≠ unfindable, only sorted lower.
- `Convention` and `Decision` nodes get a much longer half-life (stable knowledge).

Goal: faster retrieval **and lower token cost** — the client receives the small,
currently-relevant set first, not the whole mind.

## 6. Retrieval — how "always consult the hive" is enforced

Skills are model-invoked and therefore optional — the wrong layer for "always". Layering:

1. **Read side = deterministic hook.** The plugin ships a `UserPromptSubmit` hook that
   POSTs the prompt to `/recall` and injects the returned context block. Harness-executed;
   the model cannot skip it. This is also where a pending governance chore piggybacks.
2. **Write side = standing instructions** (plugin skill + CLAUDE.md guidance): write back
   to the hive when something is reusable, suggest promotions when knowledge crosses contexts.
3. **Skills teach the *how*** (good memory writing, when to relate/promote) — never the *whether*.

Packaging: one **Claude Code plugin** = MCP server config + hooks + skills. Install, set
`HIVE_URL`/`HIVE_TOKEN`, done.

## 7. Write path

`hive_remember` writes **directly** (no human review) through a deterministic write-gate:
- **Quality gate**: minimum title and content length — a memory must be specific,
  searchable and self-contained, or it is rejected with instructions to improve it.
- **PII filter**: e-mail, phone, IBAN, BSN-like patterns → rejected with explanation
  (the bee rephrases without the personal data).
- **Dedup, two bands**: similarity ≥ `DEDUP_SIMILARITY_THRESHOLD` (0.92) → not created,
  the existing node is touched and returned. Grey zone ≥ `DEDUP_REVIEW_THRESHOLD`
  (0.80) → created, **but a dedup chore is auto-filed** so the swarm judges whether it
  is really new. Nothing similar slips in silently.
- **Topic-sprawl prevention**: parent topics are matched semantically against existing
  topics first (`TOPIC_SIMILARITY_THRESHOLD`, 0.85) — "Fabric werkwijze" links under the
  existing "Fabric werkwijzen" instead of creating a near-duplicate topic. Only a
  genuinely new subject creates a topic (reported back to the caller).
- **Provenance**: every node records `created_by` (account) and `created_by_model`.
- Default scope: **team** (falls back to org when the account has no team). Topics are
  org-scoped structure.

## 8. Governance — the swarm maintains the hive

Creation is direct; **mutation is consensus-gated**:
- A bee that thinks a memory is stale/wrong/generic files a **suggestion**
  (`hive_suggest`): edit, invalidate, dedup-merge, promotion, or scope-widening.
  Identical suggestions (same `suggestion_key`) accumulate **votes**; one vote per
  account+model combination.
- At `CONSENSUS_THRESHOLD` distinct votes the chore becomes **ready** — except
  **scope-widening (team → org), the one mutation the swarm may NOT resolve**: it becomes
  `awaiting_human` and is decided in the admin API. Swarm handles structure; humans decide
  visibility boundaries. (Prevents client-specific knowledge leaking org-wide via promotion.)
- **Distributed upkeep**: there is no central maintenance process. `/recall` and
  `hive_search` mention how many chores are ready; a bee that is reading/writing anyway
  calls `hive_chores` and resolves one (`hive_resolve_chore`). Piggybacked maintenance —
  the hive maintains itself.
- Promotion keeps the node's original scope (visibility never widens silently).

## 9. Skills registry

Skills are `:Skill` nodes plus attached `:SkillFile` nodes (`SKILL.md` + resources) in the
Claude Code skill format. `skill_list` / `skill_get` let any client fetch and use them;
`skill_put` publishes one (a `SKILL.md` file is required, the PII filter covers all file
contents). **The creator may update their own skill directly; anyone else goes through
`hive_suggest`** — skills are knowledge, so mutations stay consensus-gated.

## 10. Secrets vault

- Fresh component. `:Secret` nodes: Fernet-encrypted value, owner account, per-secret
  grants (`[:GRANTED]`), **audit node on every read**.
- **Secrets never enter chat context**: there is deliberately **no MCP `secret_get` tool**.
  Retrieval is REST (`GET /secrets/{name}`) via the plugin's `hive-secret` script, intended
  for env injection: `export X=$(hive-secret NAME)`.
- Highest-risk block: tokens are short-lived/rotatable, grants are per-secret, audit is
  append-only.

## 11. Admin surface

Bearer `ADMIN_TOKEN` (env) on `/admin/*`: manage orgs/teams/accounts, issue/revoke account
tokens (plaintext shown once), grant secrets, and the **human review queue** for
`awaiting_human` chores (approve/reject scope-widening).

## 12. v1 scope & open items

**In v1**: everything above, plus the **hive GUI** at `/ui` (2026-07-25): a dependency-free
single page (works offline) with an interactive force-directed graph of the mind
(click = detail, double-click = expand neighborhood), semantic search, the swarm chore
queue (resolve buttons for maintainers), the human review queue (org_admins) and basic
account/token administration. Browsing the GUI does not rejuvenate memories — only
actual use does.
**Deliberately later**: rate
limiting, full-text index for fallback search, backup automation (volume snapshots for
now), skill versioning, embedding re-indexing job, CI + test suite, chore claiming/locking
(v1 relies on `ready` → first-resolver-wins; races are benign at current scale).
