# HiveMind — TODO

Status: v0.1 werkt end-to-end (27/27 smoke-checks, alles-in-één container, lokale
embeddings). Dit is wat er nog open staat, ruwweg op volgorde van belangrijkheid.

## Naar echt gebruik
- [ ] **Plugin in Claude Code installeren en er echt mee werken** (per project via `hive-init`,
      opt-in) — de skill-instructies, recall-ranking en decay-parameters slijpen zich pas in de praktijk bij.
- [ ] **Server-deploy in huisstijl** (compose op de server + Caddy-sidecar HTTPS) zodra gewenst.
- [ ] **Remote toegang via VPN** (2026-07-26): de Tritium-H5 met OpenVPN is volledig van het
      netwerk verdwenen (geen ping/ARP/SSH — fysiek nakijken: voeding/SD-kaart). Beslissen:
      board herstellen óf VPN (VPN/OpenVPN) op de server draaien; daarna wijst
      HIVE_URL remote naar de hive.
- [ ] **Mind export/import & sync**: export van (een deel van) de graph, import in een andere
      hive, en eventueel sync tussen hives — nodig zodra er meer dan één omgeving is.
- [ ] **Backups automatiseren**: `scripts/backup.sh` bestaat (stop → tar volume → start);
      periodiek draaien + bewaarbeleid.

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
- [ ] Decay-parameters tunen op basis van echt gebruik (half-lifes, gewichten; DEDUP_REVIEW_THRESHOLD
      0.80 bleek bij de werk-import aan de lage kant voor dichte corpora — 16 grey-zone chores).
- [ ] GUI verder aanscherpen (relatie-labels + pijlen zijn er sinds 2026-07-26; design-polish,
      node-bewerking via suggesties, audit-inzage nog open).
- [ ] Decision-extractie voortzetten: bees leggen expliciete besluiten voortaan apart vast
      (skill-instructie); bestaande corpus verder nalopen op impliciete besluiten.
- [ ] Meerdere orgs op één deployment actief gebruiken (datamodel ondersteunt het al).
