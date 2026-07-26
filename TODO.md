# HiveMind — TODO

Status: v0.1 werkt end-to-end (27/27 smoke-checks, alles-in-één container, lokale
embeddings). Dit is wat er nog open staat, ruwweg op volgorde van belangrijkheid.

## Naar echt gebruik
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
- [ ] **Token-beheer**: tokens listen per account (nu alleen aanmaken + revoke op hash),
      rotatie-flow, opschonen van verlopen tokens.
- [ ] **Re-embedding job**: bij een modelwissel (of embeddings later aanzetten) hebben
      bestaande nodes geen/verkeerde vectors — batch-herindexering nodig.

## Robuustheid
- [ ] **Testsuite + CI** (pytest; de smoke-test leeft nu buiten de repo — omzetten naar echte tests).
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
- [ ] Decay-parameters tunen op basis van echt gebruik (half-lifes, gewichten; DEDUP_REVIEW_THRESHOLD
      0.80 bleek bij de werk-import aan de lage kant voor dichte corpora — 16 grey-zone chores).
- [ ] GUI verder aanscherpen (relatie-labels + pijlen zijn er sinds 2026-07-26; design-polish,
      node-bewerking via suggesties, audit-inzage nog open).
- [ ] Decision-extractie voortzetten: bees leggen expliciete besluiten voortaan apart vast
      (skill-instructie); bestaande corpus verder nalopen op impliciete besluiten.
- [ ] Meerdere orgs op één deployment actief gebruiken (datamodel ondersteunt het al).
