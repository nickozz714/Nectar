# HiveMind — installeren & aanzetten (instructies voor Claude)

Je hebt dit install-pakket (`hivemind-install.zip`) gekregen. Het model is **één keer
globaal installeren per machine**, daarna **per project aanzetten waar relevant**. In een
aangezet project worden org-memories automatisch bij elke prompt opgehaald (recall-hook) en
werk je met de MCP-tools (`hive_search`, `hive_remember`, …).

**Dit pakket bevat GEEN token.** Vraag de gebruiker om de gegevens hieronder.

## Wat je van de gebruiker nodig hebt
- **HIVE_URL** — bijv. `http://your-server:8642` (server-API op het LAN).
- **HIVE_TOKEN** — het account-token (per persoon/machine; los intrekbaar).
- **anchors** (optioneel, per project) — komma-lijst van topics waar dit project op leunt.
- **Op macOS met een LAN-IP: een SSH-target** `user@host` (bijv. `user@your-server`) — voor
  de eenmalige tunnel. Zie de macOS-uitleg hieronder.

## ⚠️ Belangrijk op macOS (lees dit)
De Claude Code CLI-binary kan op macOS **geen socket openen naar een privé-LAN-IP**
(192.168.x / 10.x / 172.16.x) — een bekende bug (issues #27828 / #55169). Daarom loopt de MCP
via een **localhost-tunnel** (`launchd`, `localhost:<poort>` → server). Die tunnel is
**globaal en wordt één keer opgezet** door de globale installatie — projecten aanzetten raakt
hem nooit meer aan. Nodig: **passwordless SSH naar de server**:
```bash
ssh-copy-id user@host    # eenmalig, als 'ssh user@host' nog om een wachtwoord vraagt
```
Op **Linux** speelt dit niet: de MCP praat direct met het LAN-IP (geen tunnel).

## Stap 1 — globaal installeren (één keer per machine)
```bash
unzip -o hivemind-install.zip
cd hivemind-install
# macOS (met LAN-IP): geef het ssh-target mee
./hive-install-global.sh "<HIVE_URL>" "<HIVE_TOKEN>" "user@host"
# Linux / publieke server: ssh-target mag weg
./hive-install-global.sh "<HIVE_URL>" "<HIVE_TOKEN>"
```
Dit plaatst de helper-scripts in `~/.hivemind/scripts/`, bewaart de connectie in
`~/.hivemind/config.json` (chmod 600), en zet op macOS+LAN-IP de tunnel op (idempotent —
draai je het nog eens, dan blijft een actieve tunnel ongemoeid).

## Stap 2 — aanzetten per project (waar relevant)
```bash
cd <project>
~/.hivemind/scripts/hive-enable.sh "<anchors>"     # anchors optioneel
```
Dit merget in dit project: `.claude/settings.json` (recall-hook + `HIVE_ENABLED=1` + creds)
en `.mcp.json` (de `hivemind` MCP-server, alleen hier). Geen tunnel-gedoe. Start daarna een
**nieuwe** Claude-sessie en keur de `hivemind` MCP-server goed.

> Eén-commando-variant (doet stap 1 idempotent + stap 2 voor het huidige project):
> `./install.sh "<HIVE_URL>" "<HIVE_TOKEN>" "<anchors>" "user@host"`

## Verifiëren
- `claude mcp list` → `hivemind ... ✔` (op macOS pas na de tunnel + localhost-URL).
- Of stel een projectspecifieke vraag die alleen uit de HiveMind te beantwoorden is.

## Belangrijk
- **Token niet committen.** In een git-repo: `.claude/settings.json` en `.mcp.json` in
  `.gitignore` (of `settings.local.json`).
- **In een aangezet project: geen lokale markdown-memories.** Schrijf memories in de HiveMind
  via `hive_remember` (type `decision` voor keuzes), skills via `skill_put`.
- **Bijwerken** gaat via de MCP-tool `hive_update` (of `~/.hivemind/scripts/hive-update.sh`) —
  die ververst de globale scripts; je hoeft niet opnieuw te installeren.
- Geen token? Vraag een org_admin: `hive_invite` (invite-code) of `/manage/tokens`.
