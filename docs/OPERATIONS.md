# Operations Runbook

Day-to-day running of a Nectar instance. Most of this is one click in the GUI (**Beheer**) or one
call; nothing here needs direct database access.

## Backup & restore

The whole hive — nodes, relationships, tags, and attachments — exports to a **single JSON file**.

- **Export:** GUI **Beheer → Data → Exporteren**, or `GET /export` (org_admin) → downloads
  `hivemind-backup.json`.
- **Restore:** GUI import, or `POST /import?mode=merge|replace`.
  - `merge` = upsert (safe; adds/updates).
  - `replace` = **wipe then restore** (a true restore — destructive).
- **Also back up two things the export does *not* contain:** the Neo4j `/data` volume (for a
  full-fidelity/DR restore) and the **`SECRET_MASTER_KEY`** (without it the vault can't be
  decrypted after a rebuild). Store the master key off-box, encrypted.

Recommended: a nightly volume snapshot + a periodic JSON export kept off-host.

## The maintenance scans (GUI: Beheer → Onderhoud)

All are safe: they mostly open **Pollen** (proposals) rather than changing data, and nothing is ever
hard-deleted. Run them periodically (or wire a cron to hit the endpoints).

| Scan | Effect |
|---|---|
| **Opruimen** (tidy) | proposes a topic for loose knowledge |
| **Staleness** | old-but-used knowledge → "still correct?" review-Pollen |
| **Topic-samenvattingen** | refresh per-topic summaries |
| **PageRank** | recompute structural importance |
| **Link-predictie** | propose `RELATES` links |
| **Tegenspraak** (contradiction) | surface possible truth-conflicts for the Swarm |
| **Herclassificeer gevoeligheid** | re-run the sensitivity classifier |
| **Ranker trainen** | train learning-to-rank on collected feedback |
| **Her-embedden** (reindex) | recompute all embeddings — **required after changing the embedding model** |

## Tuning

All knobs are visible read-only in **Beheer → Instellingen** with a *what / how / risk* note each.
Only the **consensus threshold** is live-editable there (`POST /manage/swarm/consensus`); the rest
are set via `.env` / `config.py` and take effect on restart. See
**[ML-AND-ALGORITHMS.md](ML-AND-ALGORITHMS.md)** for what each does.

Common ones:
- Small/solo swarm: set `CONSENSUS_THRESHOLD=1` so one vote is enough.
- Too many grey-band dedup Pollen on a dense corpus: raise `DEDUP_REVIEW_THRESHOLD`.
- Recall feels noisy: lower `RECALL_MAX_MEMORIES` or raise `RECALL_REL_FLOOR`.

## Upgrading / deploying

1. Ship the new code (rsync `server/src`, or pull) and `docker compose up -d --build` (or roll the
   image on ACA/K8s).
2. **Migrations run idempotently on startup** (`components/db.py`): indexes, constraints, and
   backfills. No manual DB steps.
3. Verify: `GET /health` → 200, then open `/ui`.

**Never run a bulk write straight against Neo4j on a live instance.** Add it to the `MIGRATIONS`
list in `db.py` instead — it runs inside the app (keeping audit/embedding invariants) on the next
deploy, and is idempotent so re-deploys are safe.

## Accounts, tokens, invites (Beheer → Toegang)

- Create accounts (with the person behind them) and mint tokens (with a label, optional role and
  expiry). A token value is shown **once**.
- **Invites** let someone self-register with a fixed role — no pre-made account needed.
- **Rotate** a token (revokes the old, mints a new with the same label) or **revoke** it (instant
  cut-off). **Cleanup** removes expired/revoked tokens.
- Offboarding = revoke that person's tokens; the audit trail retains what they did.

## Observability

- **Health:** `GET /health`.
- **Insight:** GUI **Beheer → Inzicht** (totals, Bloom lifecycle, most-used, knowledge gaps) and
  **Governance** (scope/type/sensitivity/provenance + Pollen pipeline).
- **Audit:** `GET /graph/audit` / GUI **Governance → Audit-trail** — every mutation and secret read.
- **Logs:** container stdout (`LOG_LEVEL`, default `INFO`). Neo4j logs inside the container.
- **Knowledge gaps:** repeated empty recalls become `:Gap` nodes — a signal of what the hive is
  missing; review them in Inzicht.
