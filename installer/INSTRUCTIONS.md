# HiveMind — installeren in dit project (instructies voor Claude)

Je hebt dit install-pakket (`hivemind-install.zip`) in een project gekregen. Doel: dit
project koppelen aan de HiveMind zodat relevante org-memories automatisch bij elke prompt
worden opgehaald (recall-hook) en je met `hive_search` / `hive_remember` e.d. kunt werken
(MCP-tools).

**Dit pakket bevat GEEN token.** Vraag de gebruiker om de gegevens hieronder.

## Wat je van de gebruiker nodig hebt
- **HIVE_URL** — bijv. `http://your-server:8642` (server-API op het LAN).
- **HIVE_TOKEN** — het account-token (per persoon/machine; los intrekbaar).
- **anchors** (optioneel) — komma-lijst van topics waar dit project op leunt.
- **Op macOS met een LAN-IP: een SSH-target** `user@host` (bijv. `user@your-server`).
  Zie de macOS-uitleg hieronder — zonder dit werken de MCP-tools niet.

## ⚠️ Belangrijk op macOS (lees dit)
De Claude Code CLI-binary kan op macOS **geen socket openen naar een privé-LAN-IP**
(192.168.x / 10.x / 172.16.x) — een bekende bug (de CLI mist de "Local Network"-permissie;
zie claude-code issues #27828 en #55169). Gevolg: `claude mcp list` geeft
`FailedToOpenSocket`, terwijl curl, node én de recall-hook (curl) wél verbinden.

**Oplossing (regelt de installer voor je):** de MCP loopt via een **localhost-tunnel**.
De installer zet een persistente `launchd`-tunnel op (`localhost:<poort>` → server) en zet
de MCP-URL op `http://localhost:<poort>/mcp` (loopback wordt niet geblokkeerd). Daarvoor is
**passwordless SSH naar de server** nodig — controleer/zet dat eerst op:
```bash
ssh-copy-id user@host    # eenmalig, als 'ssh user@host' nog om een wachtwoord vraagt
```
De **recall-hook** blijft gewoon het LAN-IP gebruiken (curl heeft wél netwerktoegang).
Op **Linux** speelt dit niet: daar praat de MCP direct met het LAN-IP (geen tunnel nodig).

## Installeren
```bash
unzip -o hivemind-install.zip
cd hivemind-install
# macOS (met LAN-IP): geef het ssh-target mee als 4e argument
./install.sh "<HIVE_URL>" "<HIVE_TOKEN>" "<anchors>" "user@host"
# Linux (of een publieke/hostname-server): het ssh-target mag weg
./install.sh "<HIVE_URL>" "<HIVE_TOKEN>" "<anchors>"
```
De installer (veilig, merget, overschrijft niets):
1. plaatst de hook-scripts onder `.hivemind/scripts/`;
2. merget de recall-hook + `env` in `.claude/settings.json`;
3. op macOS+LAN-IP: zet de launchd-tunnel op en richt de MCP op `localhost`; anders direct;
4. merget de `hivemind` MCP-server in `.mcp.json`.

Start daarna een **nieuwe** Claude-sessie en keur de `hivemind` MCP-server goed.

## Verifiëren
- `claude mcp list` → `hivemind ... ✔` (op macOS pas na de tunnel + localhost-URL).
- Of stel een projectspecifieke vraag die alleen uit de HiveMind te beantwoorden is.

## Belangrijk
- **Token niet committen.** In een git-repo: `.claude/settings.json`, `.mcp.json` en
  `.hivemind/` in `.gitignore` (of `settings.local.json`).
- **Memories schrijf je in de HiveMind** via `hive_remember` (type `decision` voor keuzes),
  `skill_put` / `workflow_put` — niet in losse markdown.
- Geen token? Vraag een org_admin: `hive_invite` (invite-code) of `/manage/tokens`.
