# Nectar — TODO

Status: v0.1 works end-to-end (27/27 smoke checks, all-in-one container, local
embeddings). This is what's still open, roughly in order of importance.

## Toward real use
- [x] **Self-registration + role-on-token + zero-config** (2026-07-26): `/register` (first user =
      org_admin, then invite-only via `/manage/invites`), role bound to the token, ADMIN_TOKEN
      optional, vault key auto-generated. `hive-init --register` registers and stores the token.
- [ ] **Install the plugin in Claude Code and really work with it** (per project via `hive-init`,
      opt-in) — the skill instructions, recall ranking and decay parameters only settle in with real use.
- [ ] **Server deploy in house style** (compose on the server + Caddy sidecar HTTPS) once wanted.
      Remaining: run it on the server + router port-forward (a manual step, see README).
- [x] **Governance & data sensitivity à la Purview** (2026-07-26): sensitivity classification,
      /graph/governance-dashboard, /graph/audit, person linking, /graph/lineage + GUI tab.
- [x] **Tokens tied to people + lineage** (2026-07-26): account → person; lineage per node.
- [ ] **Mind export/import & sync**: export of (part of) the graph, import into another
      hive, and optionally sync between hives — needed once there is more than one environment.
- [ ] **Automate backups**: `scripts/backup.sh` exists (stop → tar volume → start);
      run it periodically + retention policy.

## Missing functionality
- [x] **Write skills to the hive**: `skill_put` (2026-07-25) — SKILL.md required,
      PII filter over all files, author may update their own skill, others via `hive_suggest`.
- [x] **Audit visibility** (2026-07-26): /graph/audit (org_admin) + Governance tab show the
      append-only trail of every write/mutation/secret-read.
- [x] **Admin hard-delete** (2026-07-26): org_admin can permanently delete a memory
      (hive_delete / DELETE /graph/node/{uid} / GUI button) — an escape hatch outside consensus, audited.
- [x] **Token management** (2026-07-26): /admin/accounts (+ token counts), /admin/accounts/{uid}/tokens,
      /admin/tokens/{hash}/rotate (revoke+new), /admin/tokens/cleanup (drop expired/revoked);
      Beheer tab shows accounts + tokens with rotate/cleanup.
- [x] **Re-embedding job** (2026-07-26): /admin/reembed?org_uid= — batch re-indexing after a model change.

## Robustness
- [x] **Test suite + CI** (2026-07-26): 20 pytest tests (`server/tests/`) against a real Neo4j with
      a deterministic fake embedder; covers tenancy/roles/tokens, write-gate (quality/PII/dedup bands/
      sensitivity/topic reuse), multi-parent + promotion consensus + scope-widening gate, ranking
      (anchor/decision/touch) and vault. GitHub Actions `.github/workflows/ci.yml` (Neo4j service).
      README + INSTALL.md written for immediate adoption.
- [ ] **Chore claiming/locking**: right now the first resolver wins (races are harmless at this
      scale); claim cleanly with more bees.
- [ ] **Backups**: volume snapshot or `neo4j-admin database dump` periodically.
- [ ] **Rate limiting / abuse protection** on the public endpoints.
- [ ] **Full-text index** in Neo4j for the fallback search path (currently a word-CONTAINS scan).

## Built 2026-07-27
- [x] Password login (GUI + MCP) + org_admin reset; scrypt.
- [x] Microsoft Entra (Azure AD) SSO — config-driven, email mapping; `deploy/entra/README.md`.
- [x] First-time wizard: empty hive → GUI wizard creates the first account (org_admin) + token.
- [x] Install-zip downloadable from the GUI (`GET /install.zip`, baked into the image).
- [x] Session state: session_save/list/resume/delete (per account, resumable on any device).
- [x] Dedup-force on hive_remember; system memories (always in recall).
- [x] Azure Container Apps deploy possible + instructions (`deploy/azure/README.md`).

## Later / ideas
- [x] Web UI: hive GUI at `/ui` (2026-07-25) — graph explorer, search, chores, review, admin.
      Still to extend: edit nodes via suggestions from the GUI, audit visibility, teams/secrets overview.
- [x] Roles: member → maintainer → org_admin (2026-07-25) — maintenance and review are role-bound.
- [ ] Skill versioning.
- [x] Dedup threshold adjusted (2026-07-26): DEDUP_REVIEW_THRESHOLD 0.80 → 0.85 (dense
      work corpora gave too many grey-zone chores). Half-lives/weights: tune further on real use.
- [x] GUI node editing via suggestions (2026-07-26): "Propose change" in the detail panel
      (edit/invalidate/promotion/scope_widening) → /graph/suggest, consensus-gated.
- [x] Multiple orgs visible/manageable (2026-07-26): /admin/orgs with account/node counts
      (the data model already supported it; now also visible in admin).
- [ ] Continue decision extraction: bees now record explicit decisions separately
      (skill instruction is in place); periodically re-scan the existing corpus for implicit decisions.
