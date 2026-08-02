# API & MCP Reference

Nectar exposes the same brain two ways: an **HTTP API** (for the GUI, installers, and any client)
and an **MCP server** at `/mcp` (for AI agents). All requests carry `Authorization: Bearer <token>`
unless noted. Roles: `member < maintainer < org_admin`; `admin` = operator `ADMIN_TOKEN` header.

## MCP tools (agent surface, `/mcp`)

The tools an agent uses. Load them via any MCP client; the server's own instructions tell connecting
models how to use recall + write + feedback out of the box.

| Tool | Does |
|---|---|
| `hive_recall(query, anchors?, project?)` | **The main entry point.** Returns the full context block: active focus + standing instructions + top-ranked memories + one contextual Pollen. Client-agnostic. |
| `hive_search(query, tags?)` | Ranked search hits (no rejuvenation). |
| `hive_get(uid)` | One memory + its files/relations (scope-checked). |
| `hive_remember(type, title, content, scope, …)` | Write a memory through the write-gate. |
| `hive_learn(...)` | Shorthand to record a `learning`. |
| `hive_feedback(node_uid, helped)` | Report whether a recalled memory helped (Memory Worth). |
| `hive_suggest(kind, node_uid, payload, rationale)` | Propose a consensus-gated mutation (edit/invalidate/promotion/scope_widening). |
| `hive_supersede` / `hive_update` / `hive_tag` / `hive_relate` | Truth-over-time + curation. |
| `hive_chores()` | List the Pollen queue. |
| `hive_claim` / `hive_release` | Claim a Pollen (stigmergy TTL) / release it. |
| `hive_resolve_chore(uid, apply\|reject)` | Resolve a consensus Pollen. |
| `hive_resolve_think(uid, ADD\|UPDATE\|DELETE\|NOOP, …)` | Resolve an `op_route` near-duplicate think-Pollen. |
| `hive_resolve_contradiction(uid, contradiction\|compatible, current?, outdated?)` | Judge a contradiction-check think-Pollen. |
| `focus_set` / `focus_advance` / `focus_get` / `focus_clear` | The active-task steering state (per project). |
| `skill_put` / `skill_get` / `skill_list` / `workflow_put` | File-backed skills & workflows. |
| `topic_create` / `topic_list` / `topic_merge` / `node_move` | Structure the graph. |
| `hive_attachments` | Attach/list files on a memory. |
| `hive_invite` / `hive_members` / `hive_set_role` / `hive_set_password` | Membership (admin). |
| `hive_set_system` | Mark a memory as a standing instruction (always injected). |
| `session_save` / `session_list` / `session_resume` / `session_delete` | Session state helpers. |

> Note: there is **no** MCP tool that returns a secret's value — the vault is REST-only by design.

## HTTP API (selected — see the routers for the full set)

### Identity & recall
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | – | liveness |
| GET | `/graph/me` | member | identity + capability flags + ready-Pollen count |
| POST | `/recall` | member | the deterministic recall context block |
| GET | `/graph/search?q=&tags=` | member | search |

### Knowledge
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/graph/remember` | member | create a memory (write-gate) |
| GET | `/graph/node/{uid}` | member | node detail + files (scope-checked) |
| POST | `/graph/feedback` | member | Memory Worth signal |
| POST | `/graph/importance` · `/graph/decay` · `/graph/lifecycle` · `/graph/supersede` | maintainer | ranking/lifecycle controls |
| POST | `/graph/relate` · `/graph/unlink` · `/graph/node/{uid}/move` · `/graph/topics` · `/graph/topics/merge` | maintainer/member | structure |

### Governance & Pollen
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/graph/chores` | member | the swarm queue (each Pollen enriched with a human `view`) |
| POST | `/graph/suggest` | member | file a consensus mutation |
| POST | `/graph/chores/{uid}/resolve?action=apply\|reject&direct=` | maintainer/admin | resolve (direct = admin bypass) |
| POST | `/graph/think/resolve` | member | resolve op_route |
| POST | `/graph/contradiction/resolve` | member | resolve contradiction_check |
| GET | `/review/chores` · POST `/review/chores/{uid}/approve\|reject` | org_admin | scope-widening human queue |
| GET | `/graph/governance` · `/graph/analytics` · `/graph/audit` · `/graph/lineage/{uid}` | member/admin | dashboards + audit + provenance |

### Maintenance scans (maintainer)
`POST /graph/{tidy-scan, staleness-scan, topic-summaries, pagerank-scan, linkpred-scan,
contradiction-scan, reclassify-sensitivity, train-ranker}` · `POST /graph/reindex` (org_admin).

### Admin / manage (org_admin, own account token)
`/manage/accounts`, `/manage/tokens` (+ `/{hash}/rotate|revoke|role`, `/cleanup`),
`/manage/invites` (+ `/{hash}/revoke`), `/manage/teams`, `/manage/swarm` + `/manage/swarm/consensus`,
`GET /manage/settings` (read-only tuning view).

### Skills, secrets, backup, focus
`GET/POST /skills`, `GET /skills/{uid}` · `GET/PUT /secrets/{name}` (REST-only, audited) ·
`GET /export`, `POST /import?mode=merge|replace` (org_admin) · `GET/POST /focus`, `/focus/advance`,
`DELETE /focus`.

### Auth & sign-up
`POST /auth/login`, `/auth/password`, `/auth/password/for` · `GET /register`, `POST /register` ·
`GET /auth/entra/{status,login,callback}` · `GET /install.zip`, `GET /ui`.

## Connecting a generic MCP client

```jsonc
{
  "mcpServers": {
    "nectar": {
      "url": "https://<host>:8643/mcp",
      "headers": { "Authorization": "Bearer <account token>" }
    }
  }
}
```

Have the model call `hive_recall("<task>")` at the start of a task, `hive_remember` to write, and
`hive_feedback` on what helped. Claude Code gets automatic recall on every prompt via its hook; other
clients call `hive_recall` on demand for the same context.
