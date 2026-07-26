# HiveMind — TODO

Status: v0.1 werkt end-to-end (27/27 smoke-checks, alles-in-één container, lokale
embeddings). Dit is wat er nog open staat, ruwweg op volgorde van belangrijkheid.

## Naar echt gebruik
- [x] **Zelf-registratie + rol-op-token + zero-config** (2026-07-26): `/register` (eerste user =
      org_admin, daarna invite-only via `/manage/invites`), rol gebonden aan token, ADMIN_TOKEN
      optioneel, vault-key auto-gegenereerd. `hive-init --register` registreert en slaat token op.
- [ ] **Plugin in Claude Code installeren en er echt mee werken** (per project via `hive-init`,
      opt-in) — de skill-instructies, recall-ranking en decay-parameters slijpen zich pas in de praktijk bij.
- [ ] **Server-deploy in huisstijl** (compose op de server + Caddy-sidecar HTTPS) zodra gewenst.
- [x] **Remote toegang via VPN** (2026-07-26): `deploy/VPN/` — één container,
      alleen UDP 51820, per-device keys, split tunnel, geen web-UI. Boot-gevalideerd.
      Resteert: op de server draaien + KPN-router port-forward (handmatige stap, zie README).
      (Tritium-H5/OpenVPN bleek dood op het netwerk — vervangen i.p.v. herstellen.)
- [x] **Governance & datagevoeligheid à la Purview** (2026-07-26): sensitivity-classificatie,
      /graph/governance-dashboard, /graph/audit, persoon-koppeling, /graph/lineage + GUI-tab.
- [x] **Tokens aan personen + lineage** (2026-07-26): account → persoon; lineage per node.
- [ ] **Mind export/import & sync**: export van (een deel van) de graph, import in een andere
      hive, en eventueel sync tussen hives — nodig zodra er meer dan één omgeving is.
- [ ] **Backups automatiseren**: `scripts/backup.sh` bestaat (stop → tar volume → start);
      periodiek draaien + bewaarbeleid.

## Ontbrekende functionaliteit
- [x] **Skills schrijven naar de hive**: `skill_put` (2026-07-25) — SKILL.md verplicht,
      PII-filter over alle bestanden, maker mag eigen skill bijwerken, anderen via `hive_suggest`.
- [x] **Audit-inzage** (2026-07-26): /graph/audit (org_admin) + Governance-tab tonen de
      append-only trail van elke write/mutatie/secret-read.
- [x] **Token-beheer** (2026-07-26): /admin/accounts (+ token-tellingen), /admin/accounts/{uid}/tokens,
      /admin/tokens/{hash}/rotate (revoke+nieuw), /admin/tokens/cleanup (verlopen/ingetrokken weg);
      Beheer-tab toont accounts + tokens met roteren/opruimen.
- [x] **Re-embedding job** (2026-07-26): /admin/reembed?org_uid= — batch-herindexering na modelwissel.

## Robuustheid
- [x] **Testsuite + CI** (2026-07-26): 20 pytest-tests (`server/tests/`) tegen echte Neo4j met
      deterministische fake-embedder; dekt tenancy/rollen/tokens, write-gate (kwaliteit/PII/dedup-banden/
      sensitivity/topic-hergebruik), multi-parent + promotie-consensus + scope-widening-gate, ranking
      (anchor/decision/touch) en vault. GitHub Actions `.github/workflows/ci.yml` (Neo4j-service).
      README + INSTALL.md geschreven voor directe ingebruikname.
- [ ] **Chore claiming/locking**: nu wint de eerste resolver (races zijn onschuldig op deze
      schaal); netjes claimen bij meer bijen.
- [ ] **Backups**: volume-snapshot of `neo4j-admin database dump` periodiek.
- [ ] **Rate limiting / abuse-bescherming** op de publieke endpoints.
- [ ] **Full-text index** in Neo4j voor de fallback-zoekweg (nu woord-CONTAINS-scan).

## Later / ideeën
- [x] Web-UI: hive GUI op `/ui` (2026-07-25) — graph-verkenner, zoeken, chores, review, beheer.
      Nog uit te breiden: nodes bewerken via suggesties vanuit de GUI, audit-inzage, teams/secrets-overzicht.
- [x] Rollen: member → maintainer → org_admin (2026-07-25) — onderhoud en review zijn rol-gebonden.
- [ ] Skill-versionering.
- [x] Dedup-drempel bijgesteld (2026-07-26): DEDUP_REVIEW_THRESHOLD 0.80 → 0.85 (dichte
      werk-corpora gaven te veel grey-zone chores). Half-lifes/gewichten: verder tunen op echt gebruik.
- [x] GUI node-bewerking via suggesties (2026-07-26): "Wijziging voorstellen" in het detailpaneel
      (edit/invalidate/promotion/scope_widening) → /graph/suggest, consensus-gated.
- [x] Meerdere orgs zichtbaar/beheerbaar (2026-07-26): /admin/orgs met account/node-tellingen
      (datamodel ondersteunde het al; nu ook in beheer inzichtelijk).
- [ ] Decision-extractie voortzetten: bees leggen expliciete besluiten voortaan apart vast
      (skill-instructie staat); bestaande corpus periodiek nalopen op impliciete besluiten.
