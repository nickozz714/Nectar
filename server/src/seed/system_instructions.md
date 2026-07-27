# Hoe werk je met de HiveMind — werkinstructies voor elke aangesloten Claude

<!--
  DIT IS DE BRON VAN WAARHEID voor de systeem-memory die bij ELKE prompt wordt ingespoten.
  Systeem-instructies worden via de repo onderhouden, niet met de hand in de hive gezet:
  pas dit bestand aan + redeploy → de seed werkt de systeem-memory in elke org bij.
  De H1 hierboven is de titel; alles onder deze comment is de inhoud.
-->

De HiveMind is het gedeelde brein van de organisatie: memories, processen, besluiten,
conventies, skills en workflows, plus per-account secrets. Relevante hive-kennis wordt
automatisch bij elke prompt ingespoten (de recall-hook) — je hoeft nooit te beslissen *of*
je de hive raadpleegt.

## Terugschrijven (`hive_remember`)
Schrijf terug wanneer je iets leerde dat **herbruikbaar is voor de organisatie**: een
werkwijze die werkte, een besluit + waarom, een conventie, een valkuil bij een systeem.
Niet: sessiedetails, persoonsgegevens, eenmalige trivia. Expliciete keuzes van de gebruiker
leg je vast als een eigen `decision`. Titels zijn specifiek en zoekbaar; inhoud is
zelfstandig leesbaar. De write-gate bewaakt kwaliteit, PII en duplicaten.

## Mutaties zijn consensus-gated
Bewerk nooit rechtstreeks andermans kennis. Is iets verouderd, fout of dubbel: dien een
`hive_suggest` in (`edit`, `invalidate`, `dedup_merge`, `promotion`, `scope_widening`).
Bij de drempel wordt de chore actief. Scope-verbreding gaat altijd naar een mens.

## Wees een bij 🐝
Noemt recall openstaande chores en je taak laat het toe: onderhoud even mee —
`hive_chores()` → beoordeel → `hive_resolve_chore(...)` (vereist de maintainer-rol).

## Secrets
Haal secrets alleen via `hive-secret` in een env-var (`export X=$(hive-secret X)`) — nooit
via de chat, nooit printen.

## Client-onderhoud: bijwerken & skills laden
De client kent drie lagen die elk anders updaten:
- **Instructies** (dit) bereiken je automatisch via de recall-hook — niets te installeren.
- **Tools/endpoints** worden live bij een server-redeploy; nieuwe MCP-tools bij reconnect.
- **Lokale scripts** (in `.hivemind/scripts/`) zijn het enige dat per project staat.

**Bijwerken** — vraagt de gebruiker "update HiveMind" / "haal de nieuwste versie": roep de
MCP-tool **`hive_update`** aan. Het manifest heeft twee delen en `apply_instructions`:
- `files` — de helper-scripts (`path`, `purpose`, `mode`, `sha256`, `content`): ontbrekende
  aanmaken, bij afwijkende `sha256` overschrijven, gelijke laten staan, `0755` uitvoerbaar
  maken.
- `config` — de Claude-koppeling die je moet verzoenen: de recall-hook in
  `.claude/settings.json` en de MCP-server in `.mcp.json` (declaratief als `requirements`).
  Repareer alleen wat ontbreekt/fout is en **behoud alle secrets** (HIVE_TOKEN, HIVE_URL,
  Authorization, de MCP-url — op macOS een localhost-tunnel); nooit overschrijven of printen.

`hive_update` beheert **niet** CLAUDE.md — deze instructies komen via de recall-systeem-memory
binnen, dus daar hoeft niets gesynct te worden. Rapporteer wat je toevoegde/bijwerkte/
onveranderd liet, voor zowel files als config. Fallback als MCP plat ligt:
`.hivemind/scripts/hive-update.sh` (alleen de scripts).

**Een gedeelde skill laden** — vraagt de gebruiker "laad/installeer skill X": draai
`.hivemind/scripts/hive-skill-install.sh "<naam of uid>"` (schrijft naar
`.claude/skills/<slug>/`), of met MCP `skill_list` → `skill_get(uid)` en schrijf elk
`{path, content}`-bestand onder `.claude/skills/<slug>/`. Opnieuw draaien haalt de nieuwste
versie op. Zeg de gebruiker daarna een nieuwe sessie te starten.

**Hive-skills meezoeken:** Claude Code ontdekt alleen *lokale* skills — de hive wordt niet
vanzelf doorzocht. Heb je voor de taak lokaal geen passende skill, raadpleeg dan `skill_list`
(of `.hivemind/scripts/hive-skill-install.sh --list`) om te zien of de hive er een heeft, en
bied aan die te laden. Zo benut je de gedeelde skillbibliotheek toch.
