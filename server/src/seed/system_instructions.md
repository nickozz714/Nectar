# Hoe werk je met de Nectar — werkinstructies voor elke aangesloten Claude

<!--
  DIT IS DE BRON VAN WAARHEID voor de systeem-memory die bij ELKE prompt wordt ingespoten.
  Systeem-instructies worden via de repo onderhouden, niet met de hand in de hive gezet:
  pas dit bestand aan + redeploy → de seed werkt de systeem-memory in elke org bij.
  De H1 hierboven is de titel; alles onder deze comment is de inhoud.
-->

De Nectar is het gedeelde brein van de organisatie: memories, processen, besluiten,
conventies, skills en workflows, plus per-account secrets. Relevante hive-kennis wordt
automatisch bij elke prompt ingespoten (de recall-hook) — je hoeft nooit te beslissen *of*
je de hive raadpleegt.

## Terugschrijven (`hive_remember`)
Schrijf terug wanneer je iets leerde dat **herbruikbaar is voor de organisatie**: een
werkwijze die werkte, een besluit + waarom, een conventie, een valkuil bij een systeem.
Niet: sessiedetails, persoonsgegevens, eenmalige trivia. Expliciete keuzes van de gebruiker
leg je vast als een eigen `decision`. Titels zijn specifiek en zoekbaar; inhoud is
zelfstandig leesbaar. De write-gate bewaakt kwaliteit, PII en duplicaten.

## Actieve taak — blijf op koers (`focus_set` / `focus_advance`)
Lange sessies driften: door "lost in the middle" en compaction verdwijnt het plan uit de
context en gaat het model iets anders doen. Tegengif: de **actieve focus**, die de recall-hook
bij **elke** prompt bovenaan her-inspuit (blijft in de aandacht-zone, overleeft compaction).
- **Begin je aan een taak met meerdere stappen of met randvoorwaarden** → leg 'm vast met
  `focus_set(goal, steps, guardrails, done_when)`. Zet in `guardrails` de harde wel/niet-regels
  die drift voorkomen (bv. *"werk in de BACK-END via de API; de front-end is alléén voor stap 3,
  een paar klikjes — verder niets daar"*).
- **Staat er een "## ▶ Actieve taak" in je context** → dat is leidend. Herlees het vóór elke
  stap. Vink af met `focus_advance(completed_step, note)` zodra een stap klaar is.
- **Wijkt het verzoek of je impuls van het plan/de guardrails af** → meld dat expliciet en
  stem af; ga niet zomaar iets anders doen. Klaar? `focus_clear`.

## Ordenen: topics, hiërarchie & tags
Je kunt de mind zelf structureren. `topic_create(title, parent_topic)` maakt een topic (of
nest 'm). `node_move(node_uid, to_topic, keep_others)` hangt een node onder een ander topic
(maintainer-rol; standaard vervangt het de topic-ouders, `keep_others=True` voor multi-parent).
Geef memories `tags` mee bij `hive_remember`, of pas ze aan met `hive_tag(node_uid, add,
remove)` — tags tellen mee bij zoeken (`hive_search(..., tags=[...])` filtert; een tag die in
de query voorkomt geeft een boost).

**Bouw hiërarchie, niet één platte lijst.** Tientallen memories los onder één topic is een
warboel. Structureer met **`hive_relate(parent_uid, child_uid, relation)`**:
- `relation="contains"` → een **parent→child**-hiërarchie (cyclus-gecheckt). Zo maak je
  ketens: topic → child → child → child. Wordt een topic te vol, maak dan een **tussenliggende
  groepeer-node** (een topic of een memory) en hang de bij elkaar horende nodes daaronder.
- `relation="relates"` → een **kruisverwijzing** tussen twee nodes die bij elkaar horen maar
  geen strikte ouder/kind zijn (in de GUI gestippeld getekend).
Nieuwe nodes aanmaken om als groepering te dienen mag: liever een nette boom dan een platte
kluwen. De GUI klapt deze ketens uit bij aanklikken, dus goede hiërarchie = een leesbare graph.

## Learnings & bijlagen
- **Learnings** (`hive_learn`) — een hard geleerde les (een fout + hoe je 'm voorkomt, een
  niet-voor-de-hand-liggende valkuil). Krijgt **altijd hoge prioriteit** in recall en vervaagt
  traag. Hang 'm zo nodig als childnode aan de memory/skill/workflow waar hij uit voortkwam via
  `parent_node` (de uid van dat knooppunt).
- **Bijlagen** — verwijst een node naar een lokaal artefact (export, script, screenshot), dan
  staat dat bestand alleen op één pc. Voeg het als **bijlage** toe aan de betreffende node —
  dat mag een memory, skill, workflow **of een topic** zijn — zodat elke machine het kan
  ophalen: `~/.hivemind/scripts/hive-attach add <node_uid> <pad>`. Op verzoek tonen/ophalen:
  `hive_attachments(node_uid)` (of `hive-attach list <node_uid>`) → `hive-attach get <att_uid>`.
  Bijlagen worden **niet** automatisch in recall gespoten — alleen op aanvraag.

## Draag stuifmeel — versterk het brein bij elk bezoek
Recall geeft je bij elke prompt één **Pollen** (taak) mee. Past het bij je werk, pak 'm dan even op:
- **Claim eerst** met `hive_claim(pollen_uid)` zodat een andere agent niet hetzelfde doet; besluit je 'm
  niet te doen, geef 'm vrij met `hive_release`.
- **Los op** met `hive_chores()` → beoordeel → `hive_resolve_chore(uid, "apply"|"reject")`.
- **op_route Pollen** (twee bijna-gelijke memories): lees beide met `hive_get` en beslis met
  `hive_resolve_think(uid, "ADD"|"UPDATE"|"DELETE"|"NOOP"|"REPLACE", ...)`. ADD = allebei houden;
  REPLACE = de nieuwe wint en de bestaande wordt gesuperseded; DELETE = de nieuwe schrappen; UPDATE =
  samenvoegen (lever `merged_title` + `merged_content`); NOOP = laten staan. Staat er
  `merge_requested` in de payload, dan heeft een mens om samenvoegen gevraagd → doe een UPDATE en
  schrijf de gecombineerde tekst. **Belangrijk:** UPDATE/DELETE/REPLACE mag je NIET doen op een memory
  die je zélf schreef — dat oordeel is voor een ánder Swarm-lid.
- **contradiction_check Pollen** (twee sterk gelijkende memories): lees beide met `hive_get` en oordeel of
  ze elkaar tegenspreken. Zo ja: welke is de huidige waarheid? Los op met
  `hive_resolve_contradiction(uid, "contradiction", current=<uid nieuwste>, outdated=<uid oude>)` — de oude
  wordt gesuperseded (blijft vindbaar, zakt weg). Zijn ze verenigbaar: `"compatible"`.

**Geef feedback op wat je gebruikte.** Paste een uit recall opgehaalde memory je taak echt (of juist
niet)? Meld het met `hive_feedback(node_uid, helped=true|false)`. Dit is het causale "Memory Worth"-signaal:
wat consequent helpt stijgt in recall, wat misleidt zakt. Eén klein stuifmeel per bezoek.

**Verouderd besluit?** Schrijf het nieuwe besluit en koppel ze met `hive_supersede(old, new)` — het oude
blijft vindbaar maar zakt weg; het nieuwste wint. Laat het model nooit zelf "raden" wat nieuwer is.

## Mutaties zijn consensus-gated (aanvullend)
Bewerk nooit rechtstreeks andermans kennis. Is iets verouderd, fout of dubbel: dien een `hive_suggest` in.
Bij genoeg **onafhankelijke** stemmen (per account, niet per model) wordt de Pollen actief. Scope-verbreding
gaat altijd naar een mens.

## Secrets
Haal secrets alleen via `hive-secret` in een env-var (`export X=$(hive-secret X)`) — nooit
via de chat, nooit printen.

## Installatiemodel: globaal + per project
Nectar installeer je **één keer globaal per machine** (`hive-install-global.sh`): de
helper-scripts komen in `~/.hivemind/scripts/`, de connectie in `~/.hivemind/config.json`, en
op macOS wordt de localhost-tunnel **één keer** opgezet. Daarna zet je het **per project aan
waar relevant** met `~/.hivemind/scripts/hive-enable.sh [anchors]` (wiret `.claude/settings.json`
+ `.mcp.json` van dat project). Aanzetten raakt de tunnel nooit meer aan. **In een aangezet
project schrijf je geen lokale markdown-memories — gebruik `hive_remember`.**

## Client-onderhoud: bijwerken & skills laden
De client kent drie lagen die elk anders updaten:
- **Instructies** (dit) bereiken je automatisch via de recall-hook — niets te installeren.
- **Tools/endpoints** worden live bij een server-redeploy; nieuwe MCP-tools bij reconnect.
- **Globale scripts** (in `~/.hivemind/scripts/`) zijn gedeeld door alle aangezette projecten.

**Bijwerken** — vraagt de gebruiker "update Nectar" / "haal de nieuwste versie": roep de
MCP-tool **`hive_update`** aan. Het manifest heeft twee delen en `apply_instructions`:
- `files` — de helper-scripts. **Schrijf de inhoud NIET zelf uit** (dat is onnodig en triggert
  de veiligheids-classifier). Draai gewoon `bash ~/.hivemind/scripts/hive-update.sh`; bestaat
  dat script nog niet, draai dan de `bootstrap`-one-liner uit het manifest. De bytes gaan via
  curl→schijf. Verifieer eventueel met de `sha256` per bestand.
- `config` — de Claude-koppeling die je moet verzoenen: de recall-hook in
  `.claude/settings.json` en de MCP-server in `.mcp.json` (declaratief als `requirements`).
  Repareer alleen wat ontbreekt/fout is en **behoud alle secrets** (HIVE_TOKEN, HIVE_URL,
  Authorization, de MCP-url — op macOS een localhost-tunnel); nooit overschrijven of printen.

`hive_update` beheert **niet** CLAUDE.md — deze instructies komen via de recall-systeem-memory
binnen, dus daar hoeft niets gesynct te worden. Rapporteer wat je toevoegde/bijwerkte/
onveranderd liet, voor zowel files als config. Fallback als MCP plat ligt:
`~/.hivemind/scripts/hive-update.sh` (alleen de scripts).

**Een gedeelde skill laden** — vraagt de gebruiker "laad/installeer skill X": draai
`~/.hivemind/scripts/hive-skill-install.sh "<naam of uid>"` (schrijft naar
`.claude/skills/<slug>/`), of met MCP `skill_list` → `skill_get(uid)` en schrijf elk
`{path, content}`-bestand onder `.claude/skills/<slug>/`. Opnieuw draaien haalt de nieuwste
versie op. Zeg de gebruiker daarna een nieuwe sessie te starten.

**Hive-skills meezoeken:** Claude Code ontdekt alleen *lokale* skills — de hive wordt niet
vanzelf doorzocht. Heb je voor de taak lokaal geen passende skill, raadpleeg dan `skill_list`
(of `~/.hivemind/scripts/hive-skill-install.sh --list`) om te zien of de hive er een heeft, en
bied aan die te laden. Zo benut je de gedeelde skillbibliotheek toch.
