# HiveMind — TODO

Status: v0.1 werkt end-to-end (27/27 smoke-checks, alles-in-één container, lokale
embeddings). Dit is wat er nog open staat, ruwweg op volgorde van belangrijkheid.

## Naar echt gebruik
- [ ] **Plugin in Claude Code installeren en er echt mee werken** (HIVE_URL/HIVE_TOKEN/HIVE_ANCHORS)
      — de skill-instructies, recall-ranking en decay-parameters slijpen zich pas in de praktijk bij.
- [ ] **Server-deploy in huisstijl** (compose op de server + Caddy-sidecar HTTPS) zodra gewenst.

## Ontbrekende functionaliteit
- [x] **Skills schrijven naar de hive**: `skill_put` (2026-07-25) — SKILL.md verplicht,
      PII-filter over alle bestanden, maker mag eigen skill bijwerken, anderen via `hive_suggest`.
- [ ] **Audit-inzage**: elke secret-read en mutatie wordt gelogd, maar er is nog geen
      admin-endpoint om de audit-trail te bekijken.
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
- [ ] Decay-parameters tunen op basis van echt gebruik (half-lifes, gewichten, dedup-drempel).
- [ ] Meerdere orgs op één deployment actief gebruiken (datamodel ondersteunt het al).
