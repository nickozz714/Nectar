# Cognition-Pollen — optional, swarm-native world research

Status: **implemented, tests green** (2026-08-13); not yet deployed. The rollout is fully
automated: the standing instructions are repo-seeded (`server/src/seed/system_instructions.md`
now carries the cognition protocol — `seed_all` refreshes every org's SYSTEM memory at
startup), the shared `pollinate-nectar` hive skill covers cognition work, and the kit ships
`hive-worker.sh` + `com.hivemind.worker.plist.example` for a scheduled headless worker.
After deploy: enable per org with `hive_set_cognition(true)` and load the launchd agent.
Implementation notes vs the original design: researched entities are written as
**`glossary`** entries (there is no `reference` knowledge type), which also makes them
doubly trigger-safe; the daily cap is a rolling 24h window; follow-ups are filed through
`hive_resolve_cognition`'s `follow_up` parameter rather than a separate endpoint.

## 1. What & why

When a memory is written that mentions entities the hive knows nothing about, the hive can
*wonder about them*. Example: a memory mentioning **Swinkels, Bavaria and SAP** triggers a
research task; a swarm agent looks the unknowns up, discovers "Bavaria is a brand of
Swinkels Family Brewers", writes small `glossary` memories for each entity, links them to
the source memory and to each other, and — within a strict budget — may follow one
interesting thread ("which other brands does Swinkels own?").

The result: the graph grows *context around* the organisation's own knowledge, so later
recall on "Bavaria" also surfaces the SAP-migration memory that mentioned it.

**Hard requirement: it must fit the existing Swarm.** No separate pipeline, no server-side
LLM, no new queue. A cognition job is just another Pollen kind flowing through the exact
mechanics that already exist: `create_think_pollen` → `candidate_pollen` / recall's
contextual pick → `hive_claim` (TTL soft-lock, stigmergy) → agent does the thinking →
resolve → `close_chore` + audit.

## 2. Principles

1. **Server stays LLM-free.** The server only *poses* the task (event-driven, at
   write-time). Entity extraction, web search and writing happen on the LLM side — any
   connected client, or a scheduled background agent that is simply one more swarm member.
   Bonus: no search-API key on the server; the client brings its own web access.
2. **Optional, default OFF.** Org-level toggle (web-search + token cost is real money).
3. **Bounded.** Every cognition-Pollen carries a budget (max new memories, max follow-up
   depth). Curiosity is a feature; runaway crawling is not.
4. **Same quality bar.** Cognition output enters through `hive_remember`, i.e. through the
   full write-gate (quality, PII, dedup, grey-zone op_route). World knowledge gets no
   backdoor.
5. **Distinguishable.** Cognition-produced nodes are tagged so humans, decay and review
   logic can treat researched world knowledge differently from lived org knowledge.

## 3. Data model

- **New Pollen type `cognition`** — add to `POLLEN_TYPES` in
  `server/src/repository/governance_repo.py`. Created via the existing
  `create_think_pollen(...)` with `kind="cognition"`, so it is `mode='think'`,
  born `status='ready'` (one visiting agent does the work; no vote-to-consensus), and
  idempotent on `suggestion_key`.
- **Payload** (JSON on the Pollen node):

  ```json
  {
    "instruction": "Research the concepts in this memory that the hive does not know yet.",
    "budget": {"max_new": 5, "max_depth": 2},
    "round": 0
  }
  ```

  `round` counts follow-up generations; `idem_key = f"cognition:{node_uid}:{round}"` so a
  re-trigger merges instead of duplicating.
- **Org setting `cognition_enabled`** — boolean property on the `Org` node, modelled
  exactly like `consensus_threshold` (`tenancy_repo.get/set_consensus_threshold`):
  `get_cognition_enabled(session, org_uid, default=False)` / `set_cognition_enabled(...)`
  (org_admin, audited). Exposed in `org_service.get_swarm_settings` and as a toggle in the
  GUI/manage surface.
- **Config knobs** (`components/config.py`): `COGNITION_MAX_NEW_MEMORIES = 5`,
  `COGNITION_MAX_DEPTH = 2`, `COGNITION_DAILY_CAP = 20` (per org, cost brake).

## 4. Trigger (server, write path)

In `memory_service.remember()`, after the node is created and topics are linked:

```
if org.cognition_enabled
   and type_ in ("memory", "learning", "decision")
   and "world-knowledge" not in (tags or [])          # never re-trigger on cognition output
   and daily_cap_not_reached(org):
    governance_repo.create_think_pollen(
        session, account, node["uid"], "cognition",
        payload={... budget/round as above ...},
        idem_key=f"cognition:{node['uid']}:0",
    )
```

Notes:

- The server does **no** entity extraction. The Pollen just says "research the unknown
  concepts in this memory" — extraction is trivial for the claiming LLM and keeping it
  client-side keeps the server dumb and cheap.
- The `world-knowledge` tag check is the loop-breaker: cognition output never spawns
  first-round cognition jobs. Follow-up curiosity goes through the budgeted `round`
  mechanism instead (§5), so depth is bounded by construction.
- Skills/workflows/glossary writes do not trigger (little to research, high noise).
- Optional per-call opt-out later (`hive_remember(..., research=False)`); the org toggle is
  leading for v1.

## 5. Execution (LLM side, swarm-native)

The Pollen surfaces through the *existing* channels: `governance_repo.candidate_pollen`
(with embedding, so agents pick contextually relevant work) and the recall hook's
`pick_contextual_pollen`. Any member may claim it; there is no destructive action, so the
producer≠reviewer safeguard is not needed here.

Worker protocol (this is prompt/skill material for the plugin, not server code):

1. `hive_claim(pollen_uid)` — soft-lock with TTL; other agents skip it (stigmergy).
2. Read the source memory (title/content come with the Pollen via `nodes_text`).
3. Extract candidate entities: proper nouns, products, systems, organisations, acronyms.
4. For each entity: `hive_search(entity)` first.
   - Already known → optionally just `hive_relate(source, existing, "mentions")`; no write.
   - Unknown → web-search, then write **one compact `glossary` entry**:
     `hive_remember(type="glossary", title="Swinkels Family Brewers — Dutch brewer (Bavaria, …)",
     content=<2–5 sentences, self-contained, source URLs>, parent_topics=[<entity/domain topic>],
     tags=["world-knowledge"], model_name=<own model>)`.
     Scope: same as the source memory (team stays team — a team's context shouldn't leak
     org-wide via research).
5. Discovered relations become edges: `hive_relate(bavaria_uid, swinkels_uid, "is brand of")`,
   `hive_relate(source_uid, sap_uid, "mentions")`.
6. **Follow-up curiosity, budgeted:** if something genuinely worth one more hop emerged
   (e.g. "Swinkels owns more brands") *and* `round < budget.max_depth`, the worker files a
   new cognition-Pollen on the newly created node with `round+1` and the remaining budget
   (`create_think_pollen` via a small service endpoint/tool). It does **not** research it
   now — the swarm picks it up later. This is how "ah, welke merken nog meer?" happens
   without any job running unbounded.
7. Resolve: `hive_resolve_cognition(pollen_uid, summary, created_uids=[...], note=...)` —
   new thin resolver in `governance_service` mirroring `resolve_think`: validates the Pollen
   (`type == "cognition"`, status open/ready), `close_chore(..., "resolved", ...)`, audit-log
   with the created uids. A "nothing unknown found" resolution is a perfectly good outcome
   and closes the Pollen too. `hive_release` if the agent gives up (claim also expires by TTL).

### The background agent

Nothing in the hive knows or cares that it is a "background" worker: it is a normal account
token behaving as one more swarm member. Recipe (ships with the plugin as a routine/skill):
a scheduled Claude Code agent that loops `candidate_pollen` → prefers `cognition` (and other)
Pollen → claim → work → resolve. Interactive sessions may also pick cognition-Pollen up via
the recall hook, exactly like every other maintenance task — the routine just guarantees
progress when no humans are around.

## 6. Guardrails

| Risk | Answer |
|---|---|
| Runaway research / cost | Default OFF; org toggle; `max_new` per job; `max_depth` via `round`; `COGNITION_DAILY_CAP` per org. |
| Feedback loop (research on research) | `world-knowledge` tag suppresses the write-time trigger; follow-ups only via budgeted rounds. |
| Graph pollution | Full write-gate applies: quality minimums, PII filter, dedup (hard dup → touch, grey zone → op_route think-Pollen for the swarm). |
| Provenance | `tags=["world-knowledge"]`, `created_by_model`, source URLs in content, resolved Pollen keeps the summary, audit log keeps created uids. |
| Scope leaks | Cognition memories inherit the source memory's scope. |
| Duplicate work | Existing claim/TTL stigmergy; idempotent `suggestion_key`. |
| Stale world knowledge | Nothing new needed: `glossary` nodes fall under the normal decay + `stale_review` machinery. |

## 7. Implementation checklist

- [x] `components/config.py`: `COGNITION_MAX_NEW_MEMORIES`, `COGNITION_MAX_DEPTH`, `COGNITION_DAILY_CAP`
- [x] `repository/tenancy_repo.py`: `get_cognition_enabled` / `set_cognition_enabled`
- [x] `repository/governance_repo.py`: `POLLEN_TYPES += {"cognition"}`
- [x] `services/memory_service.py`: write-time trigger (gated, tag-suppressed, capped)
- [x] `services/governance_service.py`: `resolve_cognition` (+ follow-up filing helper honouring budget/round)
- [x] `services/org_service.py`: expose toggle in swarm settings (get + org_admin set, audited)
- [x] `tools/registry.py`: `hive_resolve_cognition`; toggle via manage surface
- [x] GUI/manage router: cognition toggle; queue already shows the Pollen via existing chores endpoints
- [x] Plugin: worker instructions (shared `pollinate-nectar` hive skill) + `hive-worker.sh` + launchd template
- [x] `tests/test_cognition.py`: no trigger when disabled; trigger when enabled; idempotent per round; no trigger on `world-knowledge` writes; daily cap; resolve closes + audits; follow-up refused beyond `max_depth`

## 8. Open questions (v1 answers proposed)

- **Which types trigger?** v1: `memory`, `learning`, `decision`. Not skills/workflows/glossary.
- **Entity hints in the payload?** No — extraction is the claiming LLM's job; the server stays dumb.
- **Topic placement of researched entities?** Worker creates/reuses an entity or domain topic
  (`parent_topics=["Swinkels"]`); the existing tidy/promotion loop corrects misfiles.
- **Enrich instead of create?** When the entity exists but the research adds something, the
  worker uses `hive_suggest` (edit) rather than writing a near-duplicate — the normal
  consensus path then applies.
